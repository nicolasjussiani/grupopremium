from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import PerfilUsuario
from compras.models import Material, PedidoCompra, SolicitacaoMaterial


class CnpjFornecedorPosteriorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='comprador-cnpj', password='senha-forte-123'
        )
        PerfilUsuario.objects.create(usuario=self.user, perfil='compras')
        adriana = User.objects.create_user('adriana', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=adriana, perfil='gestor')
        ceo = User.objects.create_superuser('ceo_premium', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=ceo, perfil='gestor')
        self.client.force_login(self.user)
        self.material = Material.objects.create(
            nome='Material Marketplace', quantidade_estoque=0, estoque_minimo=1
        )
        self.solicitacao = SolicitacaoMaterial.objects.create(
            material=self.material,
            quantidade_solicitada=2,
            solicitante='Comprador',
            solicitante_usuario=self.user,
            unidade_destino='Matriz',
            justificativa='Compra em marketplace',
            status='compra_externa',
        )

    def _pedido(self, status='pedido_emitido', cnpj='', solicitacao=None):
        return PedidoCompra.objects.create(
            solicitacao=solicitacao or self.solicitacao,
            fornecedor='Marketplace',
            cnpj_fornecedor=cnpj,
            valor_unitario='25.00',
            valor_total='50.00',
            prazo_entrega=date.today(),
            status=status,
        )

    def test_criacao_do_pedido_aceita_cnpj_em_branco(self):
        response = self.client.post(reverse('criar_pedido', args=[self.solicitacao.pk]), {
            'fornecedor': 'Marketplace sem CNPJ visível',
            'valor_unitario': '25',
        })

        self.assertEqual(response.status_code, 302)
        pedido = PedidoCompra.objects.get(solicitacao=self.solicitacao)
        self.assertEqual(pedido.cnpj_fornecedor, '')

    def test_cnpj_pode_ser_informado_depois_do_pedido_emitido(self):
        pedido = self._pedido()

        response = self.client.post(
            reverse('atualizar_cnpj_pedido', args=[pedido.pk]),
            {'cnpj_fornecedor': '12345678000190'},
        )

        self.assertRedirects(
            response, reverse('detalhe_solicitacao', args=[self.solicitacao.pk])
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.cnpj_fornecedor, '12.345.678/0001-90')

    def test_cnpj_nao_e_exigido_antes_da_compra(self):
        pedido = self._pedido(status='aguardando_aprovacao')

        self.client.post(
            reverse('atualizar_cnpj_pedido', args=[pedido.pk]),
            {'cnpj_fornecedor': '12345678000190'},
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.cnpj_fornecedor, '')

    def test_cnpj_invalido_nao_substitui_o_valor_salvo(self):
        pedido = self._pedido(cnpj='12.345.678/0001-90')

        self.client.post(
            reverse('atualizar_cnpj_pedido', args=[pedido.pk]),
            {'cnpj_fornecedor': '123'},
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.cnpj_fornecedor, '12.345.678/0001-90')

    def test_detalhe_mostra_campo_de_cnpj_apenas_apos_compra(self):
        emitido = self._pedido(status='pedido_emitido')
        outra_solicitacao = SolicitacaoMaterial.objects.create(
            material=self.material,
            quantidade_solicitada=1,
            solicitante='Comprador',
            solicitante_usuario=self.user,
            unidade_destino='Matriz',
            justificativa='Outra compra em marketplace',
            status='compra_externa',
        )
        aguardando = self._pedido(
            status='aguardando_aprovacao', solicitacao=outra_solicitacao
        )

        response = self.client.get(
            reverse('detalhe_solicitacao', args=[self.solicitacao.pk])
        )

        self.assertContains(response, reverse('atualizar_cnpj_pedido', args=[emitido.pk]))
        self.assertNotContains(response, reverse('atualizar_cnpj_pedido', args=[aguardando.pk]))
        response_aguardando = self.client.get(
            reverse('detalhe_solicitacao', args=[outra_solicitacao.pk])
        )
        self.assertContains(response_aguardando, 'Opcional após a compra')
