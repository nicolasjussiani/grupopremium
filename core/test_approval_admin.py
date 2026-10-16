from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import AprovacaoRegistro
from core.payment_approvals import sincronizar_aprovacao_pagamento
from financeiro.models import DocumentoFinanceiro


@override_settings(APROVADOR_PAGAMENTOS_USERNAME='luiz_teste', APROVADOR_OPERACIONAL_USERNAME='thiago_teste')
class ApprovalAdminReadOnlyTests(TestCase):
    def setUp(self):
        User.objects.create_user('luiz_teste')
        User.objects.create_user('thiago_teste')
        self.administrador = User.objects.create_superuser('admin_teste')
        self.client.force_login(self.administrador)
        documento = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='B-ADMIN', descricao='Teste', valor=100,
            situacao_pagamento='a_pagar',
        )
        self.aprovacao = sincronizar_aprovacao_pagamento(documento)

    def test_admin_consulta_mas_nao_altera_dados_assinados(self):
        url = reverse('admin:core_aprovacaoregistro_change', args=[self.aprovacao.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {
            'dados_aprovacao': '{"valor":"999.00"}', 'status': 'aprovado',
        }).status_code, 403)
        self.aprovacao.refresh_from_db()
        self.assertEqual(self.aprovacao.status, 'pendente')
        self.assertEqual(self.aprovacao.dados_aprovacao['valor'], '100.00')

    def test_admin_nao_cria_nem_apaga_decisoes_para_recuperar_autorizacao_antiga(self):
        self.assertEqual(self.client.post(reverse('admin:core_aprovacaoregistro_add')).status_code, 403)
        self.assertEqual(self.client.post(reverse(
            'admin:core_aprovacaoregistro_delete', args=[self.aprovacao.pk],
        ), {'post': 'yes'}).status_code, 403)
        model_admin = admin.site._registry[AprovacaoRegistro]
        request = self.client.get(reverse('admin:core_aprovacaoregistro_changelist')).wsgi_request
        self.assertNotIn('delete_selected', model_admin.get_actions(request))
        self.assertTrue(AprovacaoRegistro.objects.filter(pk=self.aprovacao.pk).exists())
