from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compras.models import Material, RequisicaoCompra, SolicitacaoMaterial
from core.approval_workflow import criar_fluxo_compras
from core.models import AprovacaoRegistro, PerfilUsuario


class EdicaoAprovacaoTests(TestCase):
    def setUp(self):
        self.comprador = User.objects.create_user('comprador')
        PerfilUsuario.objects.create(usuario=self.comprador, perfil='compras')
        self.adriana = User.objects.create_user('adriana')
        self.ceo = User.objects.create_user('ceo_premium')
        self.material = Material.objects.create(nome='Material', quantidade_estoque=10)
        self.rc = RequisicaoCompra.objects.create(
            solicitante='Comprador', unidade_destino='Matriz', justificativa='Reposição',
        )
        self.item = SolicitacaoMaterial.objects.create(
            requisicao=self.rc, material=self.material, quantidade_solicitada=2,
        )
        self.primeira = criar_fluxo_compras(
            objeto=self.rc, titulo='RC teste', descricao='Materiais',
            solicitado_por=self.comprador,
        )

    def decidir(self, usuario, aprovacao, acao='aprovar_registro'):
        self.client.force_login(usuario)
        return self.client.post(reverse(acao, args=[aprovacao.pk]), {
            'motivo_rejeicao': 'Revisar materiais',
        })

    def editar(self):
        self.client.force_login(self.comprador)
        return self.client.post(reverse('editar_requisicao', args=[self.rc.pk]), {
            'material': [str(self.material.pk)], 'quantidade_solicitada': ['3'],
            'unidade_destino': 'Matriz', 'justificativa': 'Reposição revisada',
        })

    def enviar_ao_ceo(self):
        self.assertEqual(self.decidir(self.adriana, self.primeira).status_code, 302)
        return AprovacaoRegistro.objects.get(object_id=self.rc.pk, nivel=2)

    def test_edicao_reinicia_fila_preserva_historico_e_permite_aprovacao_final(self):
        antiga_ceo = self.enviar_ao_ceo()
        self.assertEqual(self.editar().status_code, 302)
        self.rc.refresh_from_db()
        self.assertEqual(self.rc.status, 'aguardando_adriana')
        self.primeira.refresh_from_db()
        self.assertEqual(self.primeira.status, 'aprovado')
        self.assertEqual(self.primeira.aprovado_por, self.adriana)
        antiga_ceo.refresh_from_db()
        self.assertEqual(antiga_ceo.status, 'cancelado')
        self.assertEqual(self.decidir(self.ceo, antiga_ceo).status_code, 404)
        nova = AprovacaoRegistro.objects.get(object_id=self.rc.pk, status='pendente')
        self.assertEqual(nova.destinatario, self.adriana)
        self.assertEqual(self.decidir(self.adriana, nova).status_code, 302)
        nova_ceo = AprovacaoRegistro.objects.get(object_id=self.rc.pk, status='pendente')
        self.assertEqual(self.decidir(self.ceo, nova_ceo).status_code, 302)
        self.rc.refresh_from_db()
        self.material.refresh_from_db()
        self.assertEqual(self.rc.status, 'aprovada')
        self.assertEqual(self.rc.itens.get().status, 'atendido_interno')
        self.assertEqual(self.material.quantidade_estoque, 7)

    def test_edicao_de_rejeitada_reinicia_status_e_preserva_rejeicao(self):
        self.decidir(self.adriana, self.primeira, 'rejeitar_registro')
        self.assertEqual(self.editar().status_code, 302)
        self.rc.refresh_from_db()
        self.primeira.refresh_from_db()
        self.assertEqual(self.rc.status, 'aguardando_adriana')
        self.assertEqual(self.primeira.status, 'rejeitado')
        self.assertEqual(self.primeira.motivo_rejeicao, 'Revisar materiais')
        self.assertEqual(self.rc.itens.get().status, 'pendente')

    def verificar_conclusao_por_comprovante(self, antiga):
        def anexar(objeto, request, campo):
            if campo == 'comprovante_pagamento':
                objeto.comprovante_pagamento = 'compras/comprovante.pdf'

        with patch('core.direct_uploads.assign_direct_upload', side_effect=anexar):
            self.assertEqual(self.editar().status_code, 302)
        self.assertFalse(AprovacaoRegistro.objects.filter(
            object_id=self.rc.pk, status='pendente',
        ).exists())
        self.assertEqual(self.decidir(antiga.destinatario, antiga).status_code, 404)
        self.rc.refresh_from_db()
        self.assertEqual(self.rc.status, 'aprovada')
        self.assertEqual(self.rc.itens.get().status, 'entregue')

    def test_comprovante_cancela_fila_adriana_sem_reabrir_requisicao(self):
        self.verificar_conclusao_por_comprovante(self.primeira)

    def test_comprovante_cancela_fila_ceo_sem_reabrir_requisicao(self):
        self.verificar_conclusao_por_comprovante(self.enviar_ao_ceo())
        self.primeira.refresh_from_db()
        self.assertEqual(self.primeira.status, 'aprovado')

    def test_falha_ao_reabrir_fila_desfaz_edicao(self):
        antiga = self.enviar_ao_ceo()
        self.adriana.is_active = False
        self.adriana.save(update_fields=['is_active'])
        self.assertEqual(self.editar().status_code, 200)
        self.rc.refresh_from_db()
        antiga.refresh_from_db()
        self.assertEqual(self.rc.status, 'aguardando_ceo')
        self.assertEqual(antiga.status, 'pendente')
        self.assertEqual(self.rc.itens.get().pk, self.item.pk)
        self.assertEqual(self.rc.itens.get().quantidade_solicitada, 2)
