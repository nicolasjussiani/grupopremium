from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse
from unittest.mock import patch

from compras.models import Material, PedidoCompra, RequisicaoCompra, SolicitacaoMaterial
from core.models import LogAtividade, PerfilUsuario


class RemoverAnexoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('comprador-anexos')
        PerfilUsuario.objects.create(usuario=self.user, perfil='compras')
        self.client.force_login(self.user)
        self.req = RequisicaoCompra.objects.create(
            solicitante='Comprador', unidade_destino='Matriz', justificativa='Materiais',
            documento='compras/documento.pdf', comprovante_pagamento='compras/comprovante.pdf',
            status='aprovada',
        )
        material = Material.objects.create(nome='Material', quantidade_estoque=10)
        self.item = SolicitacaoMaterial.objects.create(
            requisicao=self.req, material=material, quantidade_solicitada=2, status='entregue',
        )
        self.pedido = PedidoCompra.objects.create(
            solicitacao=self.item, fornecedor='Fornecedor', valor_unitario=5, valor_total=10, status='concluido',
        )

    def url(self, campo='documento'):
        return reverse('remover_anexo_requisicao', args=[self.req.pk, campo])

    def test_remove_so_anexo_confirmado_sem_alterar_compra(self):
        for campo in ('documento', 'comprovante_pagamento'):
            with self.subTest(campo=campo):
                response = self.client.get(self.url(campo))
                self.assertContains(response, 'Confirmar remoção')
                self.req.refresh_from_db()
                self.assertTrue(getattr(self.req, campo))
                with patch('core.storage_organization.delete_if_unreferenced') as cleanup:
                    with self.captureOnCommitCallbacks(execute=True):
                        result = self.client.post(self.url(campo), {'confirmacao': response.context['confirmacao']})
                    cleanup.assert_called_once()
                self.assertEqual(result.status_code, 302)
                self.req.refresh_from_db()
                self.item.refresh_from_db()
                self.pedido.refresh_from_db()
                self.assertFalse(getattr(self.req, campo))
                self.assertEqual(self.req.status, 'aprovada')
                self.assertEqual(self.item.status, 'entregue')
                self.assertEqual(self.pedido.status, 'concluido')
                self.assertEqual(self.item.material.quantidade_estoque, 10)
                if campo == 'documento':
                    self.assertEqual(self.req.comprovante_pagamento.name, 'compras/comprovante.pdf')
        self.assertEqual(LogAtividade.objects.filter(acao='Remoção de anexo da requisição', usuario=self.user).count(), 2)

    def test_nao_remove_arquivo_substituido_apos_confirmacao(self):
        response = self.client.get(self.url())
        RequisicaoCompra.objects.filter(pk=self.req.pk).update(documento='compras/novo.pdf')
        self.client.post(self.url(), {'confirmacao': response.context['confirmacao']})
        self.req.refresh_from_db()
        self.assertEqual(self.req.documento.name, 'compras/novo.pdf')

    def test_sem_confirmacao_campo_invalido_e_sem_permissao(self):
        self.client.post(self.url(), {})
        self.assertEqual(self.client.post(self.url('status')).status_code, 404)
        leitor = User.objects.create_user('leitor-anexos')
        leitor.user_permissions.add(Permission.objects.get(codename='view_requisicaocompra'))
        self.client.force_login(leitor)
        self.assertRedirects(self.client.get(self.url()), reverse('dashboard'), fetch_redirect_response=False)
        self.assertRedirects(self.client.post(self.url()), reverse('dashboard'), fetch_redirect_response=False)
        self.req.refresh_from_db()
        self.assertEqual(self.req.documento.name, 'compras/documento.pdf')

    def test_csrf_e_arquivo_compartilhado(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.user)
        self.assertEqual(protegido.post(self.url(), {}).status_code, 403)
        outro = RequisicaoCompra.objects.create(
            solicitante='Outro', unidade_destino='Matriz', justificativa='Teste', documento=self.req.documento.name,
        )
        token = self.client.get(self.url()).context['confirmacao']
        with patch.object(self.req.documento.storage, 'delete') as delete:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.url(), {'confirmacao': token})
            delete.assert_not_called()
        outro.refresh_from_db()
        self.assertTrue(outro.documento)
