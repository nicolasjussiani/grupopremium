from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.models import EquipamentoManutencao, Material, PedidoCompra, RequisicaoCompra, SolicitacaoMaterial
from core.models import AprovacaoRegistro, PerfilUsuario


@override_settings(
    APROVADOR_OPERACIONAL_USERNAME='thiago_teste',
    APROVADOR_PAGAMENTOS_USERNAME='luiz_teste',
)
class ComprovanteNaoSubstituiAprovacaoTests(TestCase):
    def setUp(self):
        self.thiago = User.objects.create_user('thiago_teste')
        self.luiz = User.objects.create_user('luiz_teste')
        self.comprador = User.objects.create_user('comprador')
        PerfilUsuario.objects.create(usuario=self.comprador, perfil='compras')
        self.client.force_login(self.comprador)
        self.material = Material.objects.create(nome='Material', quantidade_estoque=10)
        self.equipamento = EquipamentoManutencao.objects.create(nome='Máquina')

    def dados(self):
        return {
            'material': str(self.material.pk), 'quantidade_solicitada': '2',
            'valor_unitario': '10,00', 'unidade_destino': 'Matriz', 'justificativa': 'Reposição',
            'manutencao_equipamento': str(self.equipamento.pk), 'manutencao_problema': 'Reparo',
            'comprovante_pagamento': SimpleUploadedFile('comprovante.pdf', b'%PDF-1.4 comprovante', content_type='application/pdf'),
        }

    def test_anexo_na_criacao_preserva_pendencias_e_apenas_thiago_decide(self):
        response = self.client.post(reverse('nova_solicitacao'), self.dados())
        self.assertEqual(response.status_code, 302)
        requisicao = RequisicaoCompra.objects.get()
        aprovacao = AprovacaoRegistro.objects.get()
        self.assertTrue(requisicao.comprovante_pagamento)
        self.assertEqual(requisicao.status, 'aguardando_ceo')
        self.assertEqual(requisicao.itens.get().status, 'pendente')
        self.assertEqual(requisicao.manutencoes.get().status, 'pendente')
        self.assertFalse(PedidoCompra.objects.exists())
        self.assertEqual(aprovacao.destinatario, self.thiago)
        self.assertEqual(aprovacao.finalidade, 'operacional')
        self.material.refresh_from_db()
        self.assertEqual(self.material.quantidade_estoque, 10)
        for usuario in (self.comprador, self.luiz):
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 404)
        self.client.force_login(self.thiago)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 302)
        requisicao.refresh_from_db()
        self.assertEqual(requisicao.status, 'aprovada')
        self.assertEqual(requisicao.itens.get().status, 'atendido_interno')
        self.assertEqual(requisicao.manutencoes.get().status, 'aguardando_manutencao')

    def test_comprovante_nao_contorna_aprovador_inativo(self):
        self.thiago.is_active = False
        self.thiago.save(update_fields=['is_active'])
        response = self.client.post(reverse('nova_solicitacao'), self.dados())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RequisicaoCompra.objects.exists())
        self.assertFalse(PedidoCompra.objects.exists())
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_editar_nao_reabre_historico_com_pedido_concluido(self):
        requisicao = RequisicaoCompra.objects.create(
            solicitante='Comprador', unidade_destino='Matriz', justificativa='Histórico',
            status='pedido', comprovante_pagamento='compras/historico.pdf',
        )
        item = SolicitacaoMaterial.objects.create(
            requisicao=requisicao, material=self.material, quantidade_solicitada=2, status='entregue',
        )
        pedido = PedidoCompra.objects.create(
            solicitacao=item, fornecedor='Fornecedor histórico', valor_unitario=10,
            valor_total=20, status='concluido', aprovado_por=self.comprador,
        )
        self.assertEqual(self.client.post(reverse('editar_requisicao', args=[requisicao.pk]), self.dados()).status_code, 302)
        requisicao.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(requisicao.status, 'pedido')
        self.assertEqual(pedido.status, 'concluido')
        self.assertEqual(requisicao.itens.get().pk, item.pk)
        self.assertEqual(requisicao.comprovante_pagamento.name, 'compras/historico.pdf')
        self.assertFalse(AprovacaoRegistro.objects.exists())
