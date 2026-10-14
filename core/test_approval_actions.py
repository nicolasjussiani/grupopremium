from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db.models.query import QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.test import Client, TestCase
from django.urls import reverse

from compras.models import Material, RequisicaoCompra
from core.approval_workflow import criar_fluxo_compras
from core.models import AprovacaoRegistro, PerfilUsuario
from core.views_aprovacao import _pendencia_para_decisao


class ApprovalButtonsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button' and attrs.get('id', '').startswith('btn-'):
            self.urls[attrs['id']] = attrs.get('data-url')


class ApprovalActionsTests(TestCase):
    def setUp(self):
        self.adriana = User.objects.create_user('adriana')
        PerfilUsuario.objects.create(usuario=self.adriana, perfil='gestor')
        self.ceo = User.objects.create_user('ceo_premium')
        self.rc = RequisicaoCompra.objects.create(
            solicitante='Comprador', unidade_destino='Matriz', justificativa='Reposição',
        )
        self.aprovacao = criar_fluxo_compras(
            objeto=self.rc, titulo='RC para análise', descricao='',
            solicitado_por=self.adriana,
        )

    def button_url(self, user, action, approval):
        self.client.force_login(user)
        response = self.client.get(reverse('aprovacoes_pendentes'))
        self.assertEqual(response.status_code, 200)
        parser = ApprovalButtonsParser()
        parser.feed(response.content.decode())
        url = parser.urls[f'btn-{action}-{approval.pk}']
        self.assertEqual(url, reverse(f'{action}_registro', args=[approval.pk]))
        return url

    def test_botao_da_lista_aprova_diretamente_com_ceo(self):
        self.client.force_login(self.adriana)
        response = self.client.get(reverse('aprovacoes_pendentes'))
        self.assertNotContains(response, f'btn-aprovar-{self.aprovacao.pk}')
        self.assertEqual(
            self.client.post(reverse('aprovar_registro', args=[self.aprovacao.pk])).status_code,
            404,
        )
        url = self.button_url(self.ceo, 'aprovar', self.aprovacao)
        self.assertRedirects(self.client.post(url), reverse('aprovacoes_pendentes'))
        self.aprovacao.refresh_from_db()
        self.rc.refresh_from_db()
        self.assertEqual(self.aprovacao.aprovado_por, self.ceo)
        self.assertEqual(self.rc.status, 'aprovada')
        self.assertEqual(AprovacaoRegistro.objects.filter(
            content_type=self.aprovacao.content_type, object_id=self.rc.pk,
        ).count(), 1)

    def test_botao_da_lista_rejeita_diretamente_com_ceo(self):
        url = self.button_url(self.ceo, 'rejeitar', self.aprovacao)
        self.assertRedirects(
            self.client.post(url, {'motivo_rejeicao': 'Revisar solicitação'}),
            reverse('aprovacoes_pendentes'),
        )
        self.aprovacao.refresh_from_db()
        self.rc.refresh_from_db()
        self.assertEqual(self.aprovacao.aprovado_por, self.ceo)
        self.assertEqual(self.rc.status, 'rejeitada')
        self.assertEqual(AprovacaoRegistro.objects.filter(
            content_type=self.aprovacao.content_type, object_id=self.rc.pk,
        ).count(), 1)

    def verificar_ordem_dos_bloqueios(self, acao):
        self.client.force_login(self.ceo)
        bloqueios = []
        obter = QuerySet.get

        def registrar(queryset, *args, **kwargs):
            if queryset.query.select_for_update:
                bloqueios.append(queryset.model)
            return obter(queryset, *args, **kwargs)

        with patch.object(QuerySet, 'get', registrar):
            response = self.client.post(reverse(acao, args=[self.aprovacao.pk]), {
                'motivo_rejeicao': 'Revisar solicitação',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(bloqueios[:2], [RequisicaoCompra, AprovacaoRegistro])
        self.aprovacao.refresh_from_db()
        self.rc.refresh_from_db()
        self.assertEqual(self.aprovacao.aprovado_por, self.ceo)
        self.assertEqual(self.rc.status, 'aprovada' if acao == 'aprovar_registro' else 'rejeitada')

    def test_aprovacao_bloqueia_origem_antes_da_fila_e_conclui_callback(self):
        self.verificar_ordem_dos_bloqueios('aprovar_registro')

    def test_rejeicao_bloqueia_origem_antes_da_fila_e_conclui_callback(self):
        self.verificar_ordem_dos_bloqueios('rejeitar_registro')

    def decidir_com_alteracao_antes_do_bloqueio(self, alterar):
        """Simula outra operação concluída após a primeira leitura da fila."""
        alterou = False

        def obter(queryset, *args, **kwargs):
            nonlocal alterou
            if (
                isinstance(queryset, QuerySet)
                and queryset.model is RequisicaoCompra
                and queryset.query.select_for_update
                and not alterou
            ):
                alterou = True
                alterar()
            return get_object_or_404(queryset, *args, **kwargs)

        # TestCase mantém uma transação aberta. Chamamos a consulta diretamente
        # para que o 404 não reverta a operação concorrente simulada na conexão.
        with patch('core.views_aprovacao.get_object_or_404', side_effect=obter):
            with self.assertRaises(Http404):
                _pendencia_para_decisao(self.ceo, self.aprovacao.pk)
        self.assertTrue(alterou)

    def test_edicao_entre_leitura_e_bloqueio_impede_decidir_aprovacao_cancelada(self):
        material = Material.objects.create(nome='Material', quantidade_estoque=10)
        editor = Client()
        editor.force_login(self.adriana)

        def editar():
            response = editor.post(reverse('editar_requisicao', args=[self.rc.pk]), {
                'material': [str(material.pk)], 'quantidade_solicitada': ['3'],
                'unidade_destino': 'Matriz', 'justificativa': 'Solicitação revisada',
            })
            self.assertEqual(response.status_code, 302)

        self.decidir_com_alteracao_antes_do_bloqueio(editar)
        self.aprovacao.refresh_from_db()
        self.rc.refresh_from_db()
        material.refresh_from_db()
        self.assertEqual(self.aprovacao.status, 'cancelado')
        self.assertIsNone(self.aprovacao.aprovado_por)
        self.assertEqual(self.rc.status, 'aguardando_ceo')
        self.assertEqual(self.rc.itens.get().status, 'pendente')
        self.assertEqual(material.quantidade_estoque, 10)
        nova = AprovacaoRegistro.objects.get(object_id=self.rc.pk, status='pendente')
        self.assertNotEqual(nova.pk, self.aprovacao.pk)

    def test_exclusao_entre_leitura_e_bloqueio_impede_decidir_objeto_removido(self):
        editor = Client()
        editor.force_login(self.adriana)

        def excluir():
            response = editor.post(reverse('excluir_requisicao', args=[self.rc.pk]))
            self.assertEqual(response.status_code, 302)

        self.decidir_com_alteracao_antes_do_bloqueio(excluir)
        self.assertFalse(RequisicaoCompra.objects.filter(pk=self.rc.pk).exists())
        self.assertFalse(AprovacaoRegistro.objects.filter(pk=self.aprovacao.pk).exists())
