from datetime import date

from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse

from .models import AuditoriaItem, DocumentoFinanceiro, LancamentoERP


class CancelamentoDocumentoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('financeiro-cancelamento', password='test')
        self.client.force_login(self.user)
        self.doc = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='CANCELAR-1', descricao='Documento duplicado',
            valor=150, status='em_auditoria', situacao_pagamento='a_pagar',
            arquivo_pdf=b'%PDF-fixture',
        )
        self.url = reverse('cancelar_documento', args=[self.doc.pk])

    def lancamento(self, status='em_validacao'):
        return LancamentoERP.objects.create(
            documento=self.doc, descricao='Material', tipo='debito', valor=150,
            centro_custo='ADM', competencia=date(2026, 9, 1), status=status,
        )

    def cancelar(self, motivo='Documento duplicado'):
        return self.client.post(self.url, {'motivo': motivo})

    def test_confirmacao_nao_cancela_e_motivo_e_obrigatorio(self):
        self.assertContains(self.client.get(self.url), 'Confirmar cancelamento')
        self.assertEqual(self.cancelar('   ').status_code, 400)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'em_auditoria')
        self.assertIsNone(self.doc.cancelado_em)

    def test_preserva_historico_e_arquivo_e_retira_pendencias(self):
        item = AuditoriaItem.objects.create(documento=self.doc, item='valor_correto', status='ok')
        lancamento = self.lancamento()
        self.assertEqual(self.cancelar().status_code, 302)
        self.doc.refresh_from_db()
        lancamento.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(self.doc.status, 'cancelado')
        self.assertEqual(self.doc.cancelado_por, self.user)
        self.assertIsNotNone(self.doc.cancelado_em)
        self.assertEqual(self.doc.motivo_cancelamento, 'Documento duplicado')
        self.assertEqual(lancamento.status, 'cancelado')
        self.assertEqual(item.status, 'ok')
        self.assertEqual(bytes(self.doc.arquivo_pdf), b'%PDF-fixture')
        self.assertEqual(self.client.get(reverse('download_pdf_financeiro', args=[self.doc.pk])).content, b'%PDF-fixture')
        painel = self.client.get(reverse('painel_financeiro'), {'pagamento': 'a_pagar'})
        self.assertEqual(list(painel.context['pagamentos']), [])
        self.assertEqual(list(painel.context['docs_pendentes']), [])
        self.assertEqual(list(painel.context['lancamentos_pendentes']), [])
        self.assertContains(self.client.get(reverse('painel_financeiro'), {'pagamento': 'cancelado'}), 'CANCELAR-1')

    def test_cancelado_nao_pode_ser_pago_auditado_lancado_ou_validado(self):
        lancamento = self.lancamento()
        self.cancelar()
        for nome, pk, dados in [
            ('atualizar_pagamento_documento', self.doc.pk, {'situacao_pagamento': 'pago', 'data_pagamento': '2026-09-28'}),
            ('auditoria_documento', self.doc.pk, {}),
            ('lancar_erp', self.doc.pk, {'descricao': 'Outro'}),
            ('validar_lancamento', lancamento.pk, {'acao': 'validar'}),
            ('validar_lancamento', lancamento.pk, {'acao': 'rejeitar', 'motivo_rejeicao': 'Reabrir'}),
        ]:
            with self.subTest(nome=nome, dados=dados):
                self.assertEqual(self.client.post(reverse(nome, args=[pk]), dados).status_code, 302)
                self.doc.refresh_from_db()
                self.assertEqual(self.doc.status, 'cancelado')
                self.assertEqual(self.doc.situacao_pagamento, 'a_pagar')
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.status, 'cancelado')
        self.assertEqual(self.doc.lancamentos.count(), 1)
        detalhe = self.client.get(reverse('detalhe_documento', args=[self.doc.pk]))
        self.assertContains(detalhe, 'Documento cancelado')
        self.assertNotContains(detalhe, 'Salvar pagamento')
        self.assertNotContains(detalhe, 'Confirmar cancelamento')

    def test_repeticao_preserva_autor_data_e_motivo(self):
        self.cancelar()
        self.doc.refresh_from_db()
        momento = self.doc.cancelado_em
        self.cancelar('Novo motivo')
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.cancelado_em, momento)
        self.assertEqual(self.doc.motivo_cancelamento, 'Documento duplicado')

    def test_impede_cancelar_documento_pago_arquivado_ou_lancamento_concluido(self):
        for campo, valor in [('situacao_pagamento', 'pago'), ('status', 'arquivado')]:
            with self.subTest(campo=campo):
                anterior = getattr(self.doc, campo)
                setattr(self.doc, campo, valor)
                self.doc.save()
                self.cancelar()
                self.doc.refresh_from_db()
                self.assertIsNone(self.doc.cancelado_em)
                setattr(self.doc, campo, anterior)
                self.doc.save()
        for status in ['validado', 'finalizado']:
            with self.subTest(status=status):
                lancamento = self.lancamento(status)
                self.cancelar()
                self.doc.refresh_from_db()
                self.assertIsNone(self.doc.cancelado_em)
                lancamento.delete()

    def test_permissao_e_csrf(self):
        leitor = User.objects.create_user('leitor-cancelamento')
        leitor.user_permissions.add(Permission.objects.get(codename='view_documentofinanceiro'))
        self.client.force_login(leitor)
        self.assertEqual(self.cancelar().status_code, 403)
        self.assertNotContains(self.client.get(reverse('detalhe_documento', args=[self.doc.pk])), 'Cancelar documento')
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.user)
        self.assertEqual(protegido.post(self.url, {'motivo': 'Duplicado'}).status_code, 403)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'em_auditoria')
