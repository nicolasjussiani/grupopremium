from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from admissional.models import Colaborador, PagamentoColaborador
from admissional.services.importacao_acervo import registrar_distrato_documentado
from core.models import AprovacaoRegistro, ArquivoImportado
from core.payment_approvals import sincronizar_aprovacao_pagamento


@override_settings(
    APROVADOR_PAGAMENTOS_USERNAME='luiz_teste',
    APROVADOR_OPERACIONAL_USERNAME='thiago_teste',
)
class AprovacoesRevisaoImportacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.luiz = User.objects.create_user('luiz_teste')
        cls.thiago = User.objects.create_user('thiago_teste')
        cls.usuario = User.objects.create_superuser('importador')
        cls.colaborador = Colaborador.objects.create(nome='Pessoa', tipo_contrato='clt')

    def setUp(self):
        self.client.force_login(self.usuario)
        self.arquivo = ArquivoImportado.objects.create(
            categoria='pagamento_colaborador', subcategoria='salario', area='rh',
            nome_original='comprovante.pdf',
            arquivo=SimpleUploadedFile('comprovante.pdf', b'%PDF-comprovante'),
            sha256='a' * 64, tamanho=16, status='revisar',
            metadados={'identificador_transacao': 'importacao-teste'},
        )
        self.dados = {
            'colaborador': self.colaborador.pk, 'tipo': 'salario',
            'competencia': '2026-09-01', 'valor': '2100,00',
            'data_pagamento': '2026-10-02', 'observacao': 'Comprovante revisado',
        }
        self.url = reverse('revisar_arquivo_importado', args=[self.arquivo.pk])

    def pendente(self):
        return PagamentoColaborador.objects.create(
            colaborador=self.colaborador, tipo='salario', competencia=date(2026, 9, 1),
            competencia_fim=date(2026, 9, 30), valor=Decimal('2100'),
            data_vencimento=date(2026, 9, 30), status='pendente',
            identificador_transacao='importacao-teste',
        )

    def autorizar(self, pagamento):
        aprovacao = sincronizar_aprovacao_pagamento(pagamento, self.usuario)
        aprovacao.status = 'aprovado'
        aprovacao.aprovado_por = self.luiz
        aprovacao.decidido_em = timezone.now()
        aprovacao.save()

    def test_importacao_nao_baixa_pendente_sem_autorizacao(self):
        pagamento = self.pendente()
        response = self.client.post(self.url, self.dados)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        pagamento.refresh_from_db()
        self.arquivo.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertIsNone(pagamento.data_pagamento)
        self.assertIsNone(self.arquivo.object_id)

    def test_autorizacao_permite_baixa_sem_alterar_vencimento_e_periodo(self):
        pagamento = self.pendente()
        self.autorizar(pagamento)
        self.assertRedirects(self.client.post(self.url, self.dados), reverse('arquivo_central'))
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')
        self.assertEqual(pagamento.data_pagamento, date(2026, 10, 2))
        self.assertEqual(pagamento.data_vencimento, date(2026, 9, 30))
        self.assertEqual(pagamento.competencia_fim, date(2026, 9, 30))

    def test_revisao_nao_altera_valor_autorizado_ao_confirmar_baixa(self):
        pagamento = self.pendente()
        self.autorizar(pagamento)
        response = self.client.post(self.url, {**self.dados, 'valor': '2500,00'})
        self.assertEqual(response.status_code, 200)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertEqual(pagamento.valor, Decimal('2100'))

    def test_historico_novo_pago_nao_fabrica_aprovacao(self):
        with override_settings(APROVADOR_PAGAMENTOS_USERNAME=''):
            self.assertRedirects(self.client.post(self.url, self.dados), reverse('arquivo_central'))
        self.assertEqual(PagamentoColaborador.objects.get().status, 'pago')
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_pagamento_ja_quitado_autorizado_nao_tem_valor_alterado_na_revisao(self):
        pagamento = self.pendente()
        self.autorizar(pagamento)
        pagamento.status = 'pago'
        pagamento.data_pagamento = date(2026, 10, 2)
        pagamento.save()
        response = self.client.post(self.url, {**self.dados, 'valor': '2500,00'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'não podem ser alterados pela revisão do arquivo')
        pagamento.refresh_from_db()
        self.arquivo.refresh_from_db()
        self.assertEqual(pagamento.valor, Decimal('2100'))
        self.assertEqual(pagamento.status, 'pago')
        self.assertIsNone(self.arquivo.object_id)
        aprovacao = AprovacaoRegistro.objects.get(object_id=pagamento.pk)
        self.assertEqual(aprovacao.status, 'aprovado')
        self.assertEqual(aprovacao.dados_aprovacao['valor'], '2100.00')

    def test_pagamento_ja_quitado_autorizado_aceita_comprovante_sem_mudar_dados(self):
        pagamento = self.pendente()
        self.autorizar(pagamento)
        pagamento.status = 'pago'
        pagamento.data_pagamento = date(2026, 10, 2)
        pagamento.save()
        self.assertRedirects(self.client.post(self.url, self.dados), reverse('arquivo_central'))
        pagamento.refresh_from_db()
        self.arquivo.refresh_from_db()
        self.assertEqual(pagamento.valor, Decimal('2100'))
        self.assertEqual(pagamento.status, 'pago')
        self.assertEqual(self.arquivo.object_id, pagamento.pk)
        self.assertEqual(AprovacaoRegistro.objects.count(), 1)

    def test_historico_ja_pago_sem_aprovacao_mantem_revisao_de_dados(self):
        pagamento = self.pendente()
        pagamento.status = 'pago'
        pagamento.data_pagamento = date(2026, 10, 2)
        pagamento.save()
        self.assertRedirects(self.client.post(self.url, {**self.dados, 'valor': '2500,00'}), reverse('arquivo_central'))
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.valor, Decimal('2500'))
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_distrato_historico_documentado_preserva_pagamento_sem_aprovacao(self):
        with TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'distrato.pdf'
            caminho.write_bytes(b'%PDF-distrato-historico')
            with override_settings(APROVADOR_PAGAMENTOS_USERNAME=''):
                resultado = registrar_distrato_documentado(
                    nome=self.colaborador.nome, valor=Decimal('1500'),
                    data_pagamento=date(2026, 9, 30), caminho=caminho,
                )
        pagamento = PagamentoColaborador.objects.get(pk=resultado['pagamento_id'])
        self.assertEqual(pagamento.status, 'pago')
        self.assertEqual(pagamento.tipo, 'distrato')
        self.assertFalse(AprovacaoRegistro.objects.exists())
