from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import AprovacaoRegistro
from .models import AuditoriaItem, DocumentoFinanceiro, LancamentoERP


class IntegridadeFluxoFinanceiroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ceo = User.objects.create_superuser('ceo_premium')

    def setUp(self):
        self.client.force_login(self.ceo)
        self.doc = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='FLUXO-1', descricao='Documento de teste',
            valor=150, centro_custo='ADM', status='em_auditoria',
            situacao_pagamento='a_pagar',
        )

    def checklist(self):
        for item, _ in AuditoriaItem.ITENS_CHECKLIST:
            AuditoriaItem.objects.get_or_create(documento=self.doc, item=item)
        return {f'item_{item.pk}': 'ok' for item in self.doc.auditoria.all()}

    def auditar(self, dados):
        return self.client.post(reverse('auditoria_documento', args=[self.doc.pk]), dados)

    def lancar(self):
        return self.client.post(reverse('lancar_erp', args=[self.doc.pk]), {
            'descricao': 'Material', 'tipo': 'debito', 'centro_custo': 'ADM',
            'competencia': '2026-10-01',
        })

    def test_item_pendente_revoga_aprovacao_e_impede_lancamento(self):
        dados = self.checklist()
        self.auditar(dados)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'aprovado_lancamento')
        dados[next(iter(dados))] = 'pendente'
        self.auditar(dados)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'em_auditoria')
        self.assertEqual(self.lancar().status_code, 302)
        self.assertFalse(self.doc.lancamentos.exists())
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_status_aprovado_nao_substitui_checklist_ausente_incompleto_ou_pendente(self):
        for tipo_checklist in ('ausente', 'incompleto', 'pendente'):
            with self.subTest(tipo_checklist=tipo_checklist):
                self.doc.auditoria.all().delete()
                if tipo_checklist != 'ausente':
                    self.checklist()
                    self.doc.auditoria.update(status='ok')
                    item = self.doc.auditoria.first()
                    if tipo_checklist == 'incompleto':
                        item.delete()
                    else:
                        item.status = 'pendente'
                        item.save()
                self.doc.status = 'aprovado_lancamento'
                self.doc.save()
                self.assertEqual(self.lancar().status_code, 302)
                self.doc.refresh_from_db()
                self.assertEqual(self.doc.status, 'em_auditoria')
                self.assertFalse(self.doc.lancamentos.exists())
                self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_auditoria_legada_reconstroi_itens_sem_aprovacao_automatica(self):
        existente = AuditoriaItem.objects.create(
            documento=self.doc, item='valor_correto', status='ok', observacao='Conferido antes',
        )
        url = reverse('auditoria_documento', args=[self.doc.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.doc.auditoria.count(), len(AuditoriaItem.ITENS_CHECKLIST))
        existente.refresh_from_db()
        self.assertEqual(existente.status, 'ok')
        self.assertEqual(existente.observacao, 'Conferido antes')
        self.assertFalse(self.doc.auditoria_aprovada)
        self.auditar(self.checklist())
        self.assertEqual(self.lancar().status_code, 302)
        self.assertEqual(self.doc.lancamentos.count(), 1)

    def test_auditoria_sem_itens_nao_aprova_por_post_vazio(self):
        self.auditar({})
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'em_auditoria')
        self.assertEqual(self.doc.auditoria.filter(status='pendente').count(), 6)

    def test_auditoria_de_lancamento_em_aprovacao_ou_finalizado_e_imutavel(self):
        dados = self.checklist()
        self.auditar(dados)
        self.lancar()
        lancamento = self.doc.lancamentos.get()
        aprovacao = AprovacaoRegistro.objects.get(object_id=lancamento.pk, modulo='financeiro')
        for status in ('lancado', 'arquivado'):
            with self.subTest(status=status):
                if status == 'arquivado':
                    self.client.post(reverse('aprovar_registro', args=[aprovacao.pk]))
                antes = list(self.doc.auditoria.values())
                self.assertEqual(self.auditar({chave: 'divergente' for chave in dados}).status_code, 302)
                self.doc.refresh_from_db()
                self.assertEqual(self.doc.status, status)
                self.assertEqual(list(self.doc.auditoria.values()), antes)
                self.assertEqual(self.lancar().status_code, 302)
                self.assertEqual(self.doc.lancamentos.count(), 1)

    def test_lancamento_ativo_bloqueia_reauditoria_mesmo_com_status_legado_incorreto(self):
        self.checklist()
        LancamentoERP.objects.create(
            documento=self.doc, descricao='Legado', tipo='debito', valor=150,
            centro_custo='ADM', competencia=date(2026, 10, 1), status='em_validacao',
        )
        antes = list(self.doc.auditoria.values())
        self.auditar(self.checklist())
        self.assertEqual(list(self.doc.auditoria.values()), antes)

    def test_rejeicao_ceo_permite_corrigir_auditoria_e_reenviar(self):
        self.auditar(self.checklist())
        self.lancar()
        lancamento = self.doc.lancamentos.get()
        aprovacao = AprovacaoRegistro.objects.get(object_id=lancamento.pk, modulo='financeiro')
        self.client.post(reverse('rejeitar_registro', args=[aprovacao.pk]), {
            'motivo_rejeicao': 'Conferir dados novamente',
        })
        self.auditar({})
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'em_auditoria')
        self.auditar(self.checklist())
        self.assertEqual(self.lancar().status_code, 302)
        self.assertEqual(self.doc.lancamentos.count(), 2)
        self.assertEqual(self.doc.lancamentos.filter(status='em_validacao').count(), 1)

    def test_recebimento_liquidado_nao_pode_ser_cancelado(self):
        self.doc.situacao_pagamento = 'recebido'
        self.doc.data_pagamento = date(2026, 10, 1)
        self.doc.save()
        self.assertFalse(self.doc.pode_cancelar)
        response = self.client.post(reverse('cancelar_documento', args=[self.doc.pk]), {
            'motivo': 'Documento duplicado',
        })
        self.assertEqual(response.status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'em_auditoria')
        self.assertEqual(self.doc.situacao_pagamento, 'recebido')
        self.assertEqual(self.doc.data_pagamento, date(2026, 10, 1))
        self.assertIsNone(self.doc.cancelado_em)
        self.assertNotContains(self.client.get(reverse('detalhe_documento', args=[self.doc.pk])), 'Cancelar documento')
