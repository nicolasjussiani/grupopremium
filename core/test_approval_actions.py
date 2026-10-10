from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compras.models import RequisicaoCompra
from core.approval_workflow import criar_fluxo_compras
from core.models import AprovacaoRegistro, PerfilUsuario


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

    def test_botao_da_lista_aprova_com_adriana_e_encaminha_ao_ceo(self):
        url = self.button_url(self.adriana, 'aprovar', self.aprovacao)
        self.assertRedirects(self.client.post(url), reverse('aprovacoes_pendentes'))
        self.aprovacao.refresh_from_db()
        self.rc.refresh_from_db()
        self.assertEqual(self.aprovacao.aprovado_por, self.adriana)
        self.assertEqual(self.rc.status, 'aguardando_ceo')
        final = AprovacaoRegistro.objects.get(
            content_type=self.aprovacao.content_type, object_id=self.rc.pk, nivel=2,
        )
        self.assertEqual(final.destinatario, self.ceo)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[final.pk])).status_code, 404)
        url = self.button_url(self.ceo, 'aprovar', final)
        self.assertRedirects(self.client.post(url), reverse('aprovacoes_pendentes'))
        self.rc.refresh_from_db()
        self.assertEqual(self.rc.status, 'aprovada')

    def test_botao_da_lista_rejeita_sem_encaminhar_ao_ceo(self):
        url = self.button_url(self.adriana, 'rejeitar', self.aprovacao)
        self.assertRedirects(
            self.client.post(url, {'motivo_rejeicao': 'Revisar solicitação'}),
            reverse('aprovacoes_pendentes'),
        )
        self.aprovacao.refresh_from_db()
        self.rc.refresh_from_db()
        self.assertEqual(self.aprovacao.aprovado_por, self.adriana)
        self.assertEqual(self.rc.status, 'rejeitada')
        self.assertFalse(AprovacaoRegistro.objects.filter(
            content_type=self.aprovacao.content_type, object_id=self.rc.pk, nivel=2,
        ).exists())
