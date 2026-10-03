from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compras.models import Material, PedidoCompra, RequisicaoCompra, SolicitacaoMaterial
from core.approval_workflow import criar_fluxo_compras
from core.models import AprovacaoRegistro, LogAtividade, PerfilUsuario


class EntregaComprasTests(TestCase):
    def setUp(self):
        self.comprador = User.objects.create_user('comprador-entrega')
        PerfilUsuario.objects.create(usuario=self.comprador, perfil='compras')
        self.adriana = User.objects.create_user('adriana')
        PerfilUsuario.objects.create(usuario=self.adriana, perfil='gestor')
        self.ceo = User.objects.create_superuser('ceo_premium')
        self.client.force_login(self.comprador)
        self.material = Material.objects.create(nome='Material para entrega', quantidade_estoque=10)
        self.requisicao = RequisicaoCompra.objects.create(
            solicitante='Comprador', solicitante_usuario=self.comprador,
            unidade_destino='Matriz', justificativa='Reposição', status='aprovada',
        )
        self.item = SolicitacaoMaterial.objects.create(
            requisicao=self.requisicao, material=self.material,
            quantidade_solicitada=2, status='atendido_interno',
        )
        self.url = reverse('confirmar_entrega', args=[self.item.pk])

    def pedido(self, status='pedido_emitido'):
        self.item.status = 'aguardando_entrega'
        self.item.save()
        return PedidoCompra.objects.create(
            solicitacao=self.item, fornecedor='Fornecedor',
            valor_unitario=5, valor_total=10, status=status,
        )

    def test_entrega_interna_registra_responsavel_sem_nova_baixa_de_estoque(self):
        self.assertEqual(self.requisicao.status_entrega, 'Não entregue')
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse('detalhe_requisicao', args=[self.requisicao.pk]))
        self.item.refresh_from_db()
        self.material.refresh_from_db()
        self.assertEqual(self.item.status, 'entregue')
        self.assertEqual(self.item.atendida_por, self.comprador)
        self.assertEqual(self.material.quantidade_estoque, 10)
        self.assertEqual(self.requisicao.status_entrega, 'Entregue')
        self.assertTrue(LogAtividade.objects.filter(
            usuario=self.comprador, acao='Entrega confirmada',
        ).exists())

    def test_entrega_externa_conclui_pedido_e_permanece_no_historico(self):
        pedido = self.pedido()
        painel = self.client.get(reverse('painel_compras'))
        self.assertContains(painel, self.url)
        self.client.post(self.url)
        pedido.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(pedido.status, 'concluido')
        self.assertEqual(self.item.status, 'entregue')
        painel = self.client.get(reverse('painel_compras'))
        self.assertContains(painel, pedido.numero_pedido)
        self.assertContains(painel, 'Entregue')
        self.assertNotContains(painel, self.url)
        self.assertEqual(len(painel.context['pedidos_abertos']), 0)

    def test_aprovacao_da_adriana_nao_libera_entrega_antes_do_ceo(self):
        pedido = self.pedido(status='aguardando_aprovacao')
        self.item.status = 'compra_externa'
        self.item.save()
        nivel_adriana = criar_fluxo_compras(
            objeto=pedido, titulo='Pedido de entrega', descricao='',
            solicitado_por=self.comprador,
        )
        self.client.force_login(self.adriana)
        self.client.post(reverse('aprovar_registro', args=[nivel_adriana.pk]))
        self.client.force_login(self.comprador)
        self.client.post(self.url)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'compra_externa')
        self.assertNotContains(self.client.get(reverse('painel_compras')), self.url)
        nivel_ceo = AprovacaoRegistro.objects.get(
            content_type=nivel_adriana.content_type, object_id=pedido.pk, nivel=2,
        )
        self.client.force_login(self.ceo)
        self.client.post(reverse('aprovar_registro', args=[nivel_ceo.pk]))
        self.client.force_login(self.comprador)
        self.assertContains(self.client.get(reverse('painel_compras')), self.url)
        self.client.post(self.url)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'concluido')

    def test_requisicao_pendente_ou_rejeitada_nao_permite_entrega(self):
        for status in ['aguardando_adriana', 'aguardando_ceo', 'rejeitada']:
            with self.subTest(status=status):
                self.requisicao.status = status
                self.requisicao.save()
                self.client.post(self.url)
                self.item.refresh_from_db()
                self.assertEqual(self.item.status, 'atendido_interno')
                response = self.client.get(reverse('detalhe_requisicao', args=[self.requisicao.pk]))
                self.assertNotContains(response, self.url)

    def test_compra_sem_pedido_aprovado_nao_permite_entrega(self):
        for status in ['em_cotacao', 'aguardando_aprovacao', 'reprovado']:
            with self.subTest(status=status):
                PedidoCompra.objects.filter(solicitacao=self.item).delete()
                self.pedido(status=status)
                self.client.post(self.url)
                self.item.refresh_from_db()
                self.assertEqual(self.item.status, 'aguardando_entrega')

    def test_requisicao_mostra_entrega_parcial_ate_todos_os_itens_chegarem(self):
        outro = SolicitacaoMaterial.objects.create(
            requisicao=self.requisicao, material=self.material,
            quantidade_solicitada=1, status='atendido_interno',
        )
        self.client.post(self.url)
        self.assertEqual(self.requisicao.status_entrega, 'Entrega parcial')
        painel = self.client.get(reverse('painel_compras'))
        self.assertContains(painel, 'Entrega parcial')
        self.client.post(reverse('confirmar_entrega', args=[outro.pk]))
        self.assertEqual(self.requisicao.status_entrega, 'Entregue')

    def test_get_e_repeticao_nao_duplicam_entrega(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.post(self.url)
        self.client.post(self.url)
        self.assertEqual(LogAtividade.objects.filter(acao='Entrega confirmada').count(), 1)

    def test_perfil_apenas_consulta_nao_pode_confirmar(self):
        usuario = User.objects.create_user('consulta-entrega')
        PerfilUsuario.objects.create(usuario=usuario, perfil='entregas_consulta')
        self.client.force_login(usuario)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'atendido_interno')

    def test_solicitacao_avulsa_tambem_pode_ser_entregue(self):
        pedido = self.pedido()
        self.item.requisicao = None
        self.item.save()
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse('detalhe_solicitacao', args=[self.item.pk]))
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'concluido')

    def test_pedido_gerado_de_rc_aprovada_permite_confirmar_entrega(self):
        self.item.status = 'compra_externa'
        self.item.save()
        response = self.client.post(reverse('criar_pedido', args=[self.item.pk]), {
            'fornecedor': 'Fornecedor', 'valor_unitario': '5.00',
        })
        self.assertEqual(response.status_code, 302)
        self.requisicao.refresh_from_db()
        self.assertEqual(self.requisicao.status, 'pedido')
        self.assertEqual(self.requisicao.status_entrega, 'Não entregue')
        detalhe = self.client.get(reverse('detalhe_requisicao', args=[self.requisicao.pk]))
        self.assertContains(detalhe, self.url)
        self.client.post(self.url)
        self.assertEqual(self.requisicao.status_entrega, 'Entregue')
        self.assertEqual(self.item.pedidos.get().status, 'concluido')
