from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from compras.models import Material, PedidoCompra, RequisicaoCompra, SolicitacaoMaterial
from compras.views import _carregar_reprovacoes
from core.approval_workflow import criar_fluxo_compras
from core.models import AprovacaoRegistro, PerfilUsuario


class ResponsavelReprovacaoTests(TestCase):
    def setUp(self):
        self.comprador = User.objects.create_user('comprador-reprovacao')
        PerfilUsuario.objects.create(usuario=self.comprador, perfil='compras')
        self.adriana = User.objects.create_user('adriana', first_name='Adriana', last_name='Silva')
        PerfilUsuario.objects.create(usuario=self.adriana, perfil='gestor')
        self.ceo = User.objects.create_superuser('ceo_premium', first_name='Carlos', last_name='Diretor')
        self.rc = RequisicaoCompra.objects.create(
            solicitante='Comprador', solicitante_usuario=self.comprador,
            unidade_destino='Matriz', justificativa='Reposição',
        )
        self.item = SolicitacaoMaterial.objects.create(
            requisicao=self.rc, material=Material.objects.create(nome='Produto de exemplo'),
            quantidade_solicitada=2,
        )
        self.aprovacao = criar_fluxo_compras(
            objeto=self.rc, titulo='Requisição para análise', descricao='',
            solicitado_por=self.comprador,
        )
        self.client.force_login(self.comprador)

    def detalhe(self):
        return self.client.get(reverse('detalhe_requisicao', args=[self.rc.pk]))

    def rejeitar(self, usuario, registro):
        self.client.force_login(usuario)
        response = self.client.post(reverse('rejeitar_registro', args=[registro.pk]), {
            'motivo_rejeicao': 'Compra fora do orçamento',
        })
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.comprador)

    def rejeicao_historica_adriana(self):
        self.aprovacao.status = 'rejeitado'
        self.aprovacao.nivel = 1
        self.aprovacao.destinatario = self.adriana
        self.aprovacao.aprovado_por = self.adriana
        self.aprovacao.motivo_rejeicao = 'Compra fora do orçamento'
        self.aprovacao.decidido_em = timezone.now()
        self.aprovacao.save()
        self.rc.rejeitar()

    def test_preserva_adriana_em_rejeicao_historica_no_painel_e_detalhes(self):
        self.rejeicao_historica_adriana()
        for url in [
            reverse('painel_compras'),
            reverse('detalhe_requisicao', args=[self.rc.pk]),
            reverse('detalhe_solicitacao', args=[self.item.pk]),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'Reprovado por:')
                self.assertContains(response, 'Adriana Silva')
        response = self.detalhe()
        self.assertContains(response, 'Compra fora do orçamento')
        self.aprovacao.refresh_from_db()
        self.assertContains(response, timezone.localtime(self.aprovacao.decidido_em).strftime('%d/%m/%Y %H:%M'))

    def test_identifica_ceo_sem_confundir_com_aprovacao_da_adriana(self):
        AprovacaoRegistro.objects.create(
            content_type=self.aprovacao.content_type, object_id=self.rc.pk,
            titulo='Decisão anterior à centralização', modulo='compras', nivel=1,
            status='aprovado', aprovado_por=self.adriana, destinatario=self.adriana,
            decidido_em=timezone.now() - timedelta(days=1),
        )
        self.rejeitar(self.ceo, self.aprovacao)
        response = self.detalhe()
        self.assertContains(response, 'Carlos Diretor')
        self.assertNotContains(response, 'Adriana Silva')

    def test_pedido_reprovado_nao_e_confundido_com_rc_do_mesmo_id(self):
        self.rc.status = 'aprovada'
        self.rc.save()
        self.item.status = 'compra_externa'
        self.item.save()
        pedido = PedidoCompra.objects.create(
            solicitacao=self.item, fornecedor='Fornecedor', valor_unitario=10,
            valor_total=20, status='aguardando_aprovacao',
        )
        self.assertEqual(pedido.pk, self.rc.pk)
        aprovacao = criar_fluxo_compras(
            objeto=pedido, titulo='Pedido', descricao='', solicitado_por=self.comprador,
        )
        self.rejeitar(self.ceo, aprovacao)
        self.assertContains(self.client.get(reverse('detalhe_solicitacao', args=[self.item.pk])), 'Carlos Diretor')
        self.assertNotContains(self.detalhe(), 'Reprovado por:')
        self.rc.status = 'rejeitada'
        self.rc.save()
        response = self.detalhe()
        self.assertContains(response, 'Responsável não registrado')
        self.assertNotContains(response, 'Carlos Diretor')

    def test_requisicao_reenviada_nao_mostra_reprovacao_antiga_como_atual(self):
        self.rejeitar(self.ceo, self.aprovacao)
        for status in ['aguardando_adriana', 'aguardando_ceo', 'aprovada', 'pedido']:
            self.rc.status = status
            self.rc.save()
            self.assertNotContains(self.detalhe(), 'Reprovado por:')

    def test_usuario_sem_nome_usa_login_e_usuario_removido_nao_inventa_responsavel(self):
        self.adriana.first_name = ''
        self.adriana.last_name = ''
        self.adriana.save()
        self.rejeicao_historica_adriana()
        self.assertContains(self.detalhe(), '<strong>adriana</strong>', html=True)
        self.adriana.delete()
        self.assertContains(self.detalhe(), 'Responsável não registrado')

    def test_busca_ultima_rejeicao_em_lote_priorizando_data_da_decisao(self):
        self.rc.status = 'rejeitada'
        self.rc.save()
        self.aprovacao.status = 'rejeitado'
        self.aprovacao.aprovado_por = self.adriana
        self.aprovacao.decidido_em = timezone.now()
        self.aprovacao.save()
        antiga = AprovacaoRegistro.criar_para(objeto=self.rc, titulo='Registro antigo', modulo='compras')
        antiga.status = 'rejeitado'
        antiga.aprovado_por = self.ceo
        antiga.decidido_em = timezone.now() - timedelta(days=1)
        antiga.save()
        outra = RequisicaoCompra.objects.create(
            solicitante='Outro', unidade_destino='Filial', justificativa='Outro', status='rejeitada',
        )
        with self.assertNumQueries(1):
            _carregar_reprovacoes([self.rc, outra])
        self.assertEqual(self.rc.reprovacao, self.aprovacao)
        self.assertIsNone(outra.reprovacao)
