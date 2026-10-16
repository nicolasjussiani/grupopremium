from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import AprovacaoRegistro
from core.payment_approvals import situacao_aprovacao_pagamento
from .models import DocumentoFinanceiro, LancamentoERP


@override_settings(APROVADOR_PAGAMENTOS_USERNAME='luiz_teste', APROVADOR_OPERACIONAL_USERNAME='thiago_teste')
class AprovacaoPagamentosFinanceiroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operador = User.objects.create_superuser('operador_financeiro_teste')
        cls.luiz = User.objects.create_user('luiz_teste')
        cls.thiago = User.objects.create_user('thiago_teste')

    def setUp(self):
        self.client.force_login(self.operador)
        self.dados = {
            'tipo': 'boleto', 'numero_documento': 'APROVAR-1', 'descricao': 'Material de escritório',
            'valor': '150.00', 'situacao_pagamento': 'a_pagar', 'centro_custo': 'ADM',
            'data_vencimento': '2026-10-15',
        }

    def criar(self, **extras):
        self.assertEqual(self.client.post(reverse('entrada_documento'), {**self.dados, **extras}).status_code, 302)
        return DocumentoFinanceiro.objects.get()

    def aprovacoes(self, objeto):
        return AprovacaoRegistro.objects.filter(
            content_type=ContentType.objects.get_for_model(objeto), object_id=objeto.pk,
        ).order_by('pk')

    def decidir(self, objeto, usuario=None, rejeitar=False):
        self.client.force_login(usuario or self.luiz)
        response = self.client.post(reverse('rejeitar_registro' if rejeitar else 'aprovar_registro',
            args=[self.aprovacoes(objeto).last().pk]), {'motivo_rejeicao': 'Rever documento'} if rejeitar else {})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.operador)

    def auditar(self, doc):
        self.client.post(reverse('auditoria_documento', args=[doc.pk]), {
            f'item_{item.pk}': 'ok' for item in doc.auditoria.all()
        })

    def lancar(self, doc, **extras):
        return self.client.post(reverse('lancar_erp', args=[doc.pk]), {
            'descricao': 'Material', 'tipo': 'debito', 'centro_custo': 'ADM',
            'competencia': '2026-10-01', **extras,
        })

    def baixar(self, doc, **extras):
        return self.client.post(reverse('atualizar_pagamento_documento', args=[doc.pk]), {
            'situacao_pagamento': 'pago', 'data_pagamento': '2026-10-15', **extras,
        })

    def test_saida_solicita_luiz_e_baixa_exige_decisao(self):
        doc = self.criar()
        self.assertEqual(self.aprovacoes(doc).get().destinatario, self.luiz)
        self.assertEqual(self.baixar(doc).status_code, 400)
        self.decidir(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'a_pagar')
        self.assertIsNone(doc.data_pagamento)
        self.assertEqual(self.baixar(doc).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'pago')

    def test_novo_pago_recusado_e_recebimento_nao_vai_para_luiz(self):
        response = self.client.post(reverse('entrada_documento'), {
            **self.dados, 'situacao_pagamento': 'pago', 'data_pagamento': '2026-10-15',
        })
        self.assertContains(response, 'Cadastre como A pagar')
        self.assertFalse(DocumentoFinanceiro.objects.exists())
        doc = self.criar(situacao_pagamento='recebido', data_pagamento='2026-10-15')
        self.assertEqual(doc.situacao_pagamento, 'recebido')
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_aprovacao_contabil_thiago_e_autorizacao_pagamento_luiz_sao_independentes(self):
        doc = self.criar()
        self.auditar(doc)
        self.assertEqual(self.lancar(doc).status_code, 302)
        lancamento = LancamentoERP.objects.get()
        self.assertEqual(self.aprovacoes(lancamento).get().destinatario, self.thiago)
        self.assertEqual(self.aprovacoes(lancamento).get().finalidade, 'operacional')
        self.decidir(lancamento, self.thiago)
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'arquivado')
        self.assertEqual(doc.situacao_pagamento, 'a_pagar')
        self.assertEqual(self.baixar(doc).status_code, 400)
        self.decidir(doc)
        self.assertEqual(self.baixar(doc).status_code, 302)

    def test_lancamento_nao_pode_baixar_sem_autorizacao_e_preserva_atomicidade(self):
        doc = self.criar()
        self.auditar(doc)
        self.assertEqual(self.lancar(doc, situacao_pagamento='pago', data_pagamento='2026-10-15').status_code, 200)
        self.assertFalse(LancamentoERP.objects.exists())
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'aprovado_lancamento')
        self.assertEqual(doc.situacao_pagamento, 'a_pagar')
        self.decidir(doc)
        self.assertEqual(self.lancar(doc, situacao_pagamento='pago', data_pagamento='2026-10-15').status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'pago')
        self.assertEqual(self.aprovacoes(LancamentoERP.objects.get()).get().destinatario, self.thiago)

    def test_edicao_de_centro_de_custo_requer_nova_aprovacao(self):
        doc = self.criar()
        self.decidir(doc)
        self.assertEqual(self.client.post(reverse('editar_detalhamento_documento', args=[doc.pk]), {
            'descricao': doc.descricao, 'centro_custo': 'OPERACAO', 'unidade': 'Matriz',
        }).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(situacao_aprovacao_pagamento(doc), 'pendente')
        self.assertEqual(self.aprovacoes(doc).count(), 2)
        self.assertEqual(self.baixar(doc).status_code, 400)

    def test_rejeicao_reenvio_e_cancelamento(self):
        doc = self.criar()
        self.decidir(doc, rejeitar=True)
        self.assertEqual(self.baixar(doc).status_code, 400)
        self.client.post(reverse('atualizar_pagamento_documento', args=[doc.pk]), {'situacao_pagamento': 'a_pagar'})
        self.assertEqual(self.aprovacoes(doc).count(), 1)
        url = reverse('solicitar_aprovacao_pagamento_documento', args=[doc.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.aprovacoes(doc).count(), 2)
        self.client.post(reverse('cancelar_documento', args=[doc.pk]), {'motivo': 'Duplicado'})
        self.assertEqual(self.aprovacoes(doc).last().status, 'cancelado')

    def test_dados_alterados_fora_da_tela_nao_reutilizam_autorizacao(self):
        doc = self.criar()
        self.decidir(doc)
        DocumentoFinanceiro.objects.filter(pk=doc.pk).update(valor=Decimal('999'))
        self.assertEqual(self.baixar(doc).status_code, 400)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'a_pagar')

    def test_baixa_nao_pode_ser_reaberta_para_reusar_aprovacao(self):
        doc = self.criar()
        self.decidir(doc)
        self.baixar(doc)
        self.assertEqual(self.baixar(doc, situacao_pagamento='a_pagar').status_code, 400)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'pago')

    def test_reclassificacao_interrompe_autorizacao_anterior_de_saida(self):
        doc = self.criar()
        self.decidir(doc)
        url = reverse('atualizar_pagamento_documento', args=[doc.pk])
        self.assertEqual(self.client.post(url, {'situacao_pagamento': 'a_receber'}).status_code, 302)
        self.assertEqual(self.client.post(url, {'situacao_pagamento': 'a_pagar'}).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(situacao_aprovacao_pagamento(doc), 'pendente')
        self.assertEqual(list(self.aprovacoes(doc).values_list('status', flat=True)),
                         ['aprovado', 'cancelado', 'pendente'])
        self.assertEqual(self.baixar(doc).status_code, 400)

    def test_recebido_nao_pode_ser_reaberto_ou_alterado_para_contornar_estorno(self):
        doc = self.criar(situacao_pagamento='recebido', data_pagamento='2026-10-15')
        for situacao, data in (
            ('a_pagar', ''), ('nao_informado', ''), ('a_receber', ''),
            ('pago', '2026-10-15'), ('recebido', '2026-10-16'),
        ):
            with self.subTest(situacao=situacao, data=data):
                self.assertEqual(self.baixar(doc, situacao_pagamento=situacao, data_pagamento=data).status_code, 400)
                doc.refresh_from_db()
                self.assertEqual(doc.situacao_pagamento, 'recebido')
                self.assertEqual(doc.data_pagamento.isoformat(), '2026-10-15')
        self.client.post(reverse('cancelar_documento', args=[doc.pk]), {'motivo': 'Duplicado'})
        doc.refresh_from_db()
        self.assertNotEqual(doc.status, 'cancelado')
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_detalhamento_pago_preserva_dados_autorizados_e_permite_observacao(self):
        doc = self.criar()
        self.decidir(doc)
        self.baixar(doc)
        url = reverse('editar_detalhamento_documento', args=[doc.pk])
        dados = {'descricao': doc.descricao, 'centro_custo': doc.centro_custo, 'unidade': doc.unidade}
        for campo in dados:
            with self.subTest(campo=campo):
                response = self.client.post(url, {**dados, campo: 'Alteração após pagamento'})
                self.assertContains(response, 'a descrição e a classificação da baixa devem ser preservadas')
                doc.refresh_from_db()
                self.assertEqual(getattr(doc, campo), dados[campo])
        self.assertEqual(self.client.post(url, {**dados, 'observacoes': 'Comprovante conferido'}).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.observacoes, 'Comprovante conferido')
        self.assertEqual(self.aprovacoes(doc).count(), 1)

    @override_settings(APROVADOR_PAGAMENTOS_USERNAME='')
    def test_sem_responsavel_novo_documento_e_revertido(self):
        response = self.client.post(reverse('entrada_documento'), self.dados)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'não está configurado')
        self.assertFalse(DocumentoFinanceiro.objects.exists())
