from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from compras.models import Material, PedidoCompra, SolicitacaoMaterial
from core.models import AprovacaoRegistro, PerfilUsuario


class LogicaPedidoCompraTests(TestCase):
    def setUp(self):
        self.aprovador = User.objects.create_user(
            username='aprovador-compras', password='senha-forte-123'
        )
        PerfilUsuario.objects.create(usuario=self.aprovador, perfil='compras')
        grupo, _ = Group.objects.get_or_create(name='Compras_Aprovador')
        self.aprovador.groups.add(grupo)
        self.client.force_login(self.aprovador)
        self.material = Material.objects.create(nome='Produto lógico', quantidade_estoque=0)
        self.solicitacao = SolicitacaoMaterial.objects.create(
            material=self.material,
            quantidade_solicitada=Decimal('2.50'),
            solicitante='Comprador',
            solicitante_usuario=self.aprovador,
            unidade_destino='Matriz',
            justificativa='Teste do fluxo',
            status='compra_externa',
        )

    def criar_pedido(self, **overrides):
        dados = {
            'solicitacao': self.solicitacao,
            'fornecedor': 'Fornecedor Teste',
            'valor_unitario': Decimal('10.01'),
            'valor_total': Decimal('0.01'),
            'status': 'aguardando_aprovacao',
        }
        dados.update(overrides)
        return PedidoCompra.objects.create(**dados)

    def test_modelo_recalcula_total_em_centavos(self):
        pedido = self.criar_pedido()
        self.assertEqual(pedido.valor_total, Decimal('25.03'))

    def test_impede_segundo_pedido_ativo_para_mesma_solicitacao(self):
        self.criar_pedido()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.criar_pedido(fornecedor='Outro fornecedor')

    def test_permite_nova_cotacao_apos_reprovacao(self):
        anterior = self.criar_pedido(status='reprovado')
        novo = self.criar_pedido(fornecedor='Nova cotação')
        self.assertNotEqual(anterior.pk, novo.pk)

    def test_aprovacao_na_tela_emite_pedido_e_sincroniza_fila(self):
        pedido = self.criar_pedido()
        aprovacao = AprovacaoRegistro.criar_para(
            objeto=pedido, titulo='Aprovar compra', modulo='compras',
            solicitado_por=self.aprovador,
        )

        response = self.client.post(
            reverse('aprovar_pedido', args=[pedido.pk]), {'acao': 'aprovar'}
        )

        self.assertEqual(response.status_code, 302)
        pedido.refresh_from_db()
        self.solicitacao.refresh_from_db()
        aprovacao.refresh_from_db()
        self.assertEqual(pedido.status, 'pedido_emitido')
        self.assertEqual(self.solicitacao.status, 'aguardando_entrega')
        self.assertEqual(aprovacao.status, 'aprovado')
        self.assertEqual(aprovacao.aprovado_por, self.aprovador)

    def test_aprovacao_central_produz_o_mesmo_estado(self):
        pedido = self.criar_pedido()
        aprovacao = AprovacaoRegistro.criar_para(
            objeto=pedido, titulo='Aprovar compra', modulo='compras',
            solicitado_por=self.aprovador,
        )

        response = self.client.post(reverse('aprovar_registro', args=[aprovacao.pk]))

        self.assertEqual(response.status_code, 302)
        pedido.refresh_from_db()
        self.solicitacao.refresh_from_db()
        self.assertEqual(pedido.status, 'pedido_emitido')
        self.assertEqual(self.solicitacao.status, 'aguardando_entrega')

    def test_reprovacao_reabre_solicitacao(self):
        pedido = self.criar_pedido()
        pedido.reprovar('Preço acima do orçamento')
        pedido.refresh_from_db()
        self.solicitacao.refresh_from_db()
        self.assertEqual(pedido.status, 'reprovado')
        self.assertEqual(self.solicitacao.status, 'compra_externa')
        self.assertEqual(pedido.obs, 'Preço acima do orçamento')

    def test_nao_decide_o_mesmo_pedido_duas_vezes(self):
        pedido = self.criar_pedido()
        pedido.aprovar(self.aprovador)
        with self.assertRaises(ValidationError):
            pedido.aprovar(self.aprovador)

