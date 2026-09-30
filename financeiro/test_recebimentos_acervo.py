from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied
from django.test import TestCase, RequestFactory
from django.urls import reverse

from core.models import ArquivoImportado
from core.services.processamento_storage import _data_documento
from financeiro.models import DocumentoFinanceiro


class RecebimentosAcervoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('diretoria', password='teste')
        self.client.force_login(self.user)

    def documento(self, status='a_receber'):
        return DocumentoFinanceiro.objects.create(tipo='nota_fiscal', numero_documento='NF-42',
            descricao='Serviço de lavagem', valor='100.00', situacao_pagamento=status,
            data_emissao=date(2024, 5, 10), data_vencimento=date(2024, 6, 10))

    def test_separa_entradas_saidas_e_nao_classificados(self):
        entrada = self.documento()
        saida = self.documento('a_pagar')
        incerto = self.documento('nao_informado')
        for fluxo, esperado in [('entradas', entrada), ('saidas', saida), ('classificar', incerto)]:
            response = self.client.get(reverse('painel_financeiro'), {'fluxo': fluxo})
            self.assertEqual(list(response.context['pagamentos']), [esperado])
            self.assertEqual(response.context['resumo_contas'], {'a_pagar': 100, 'a_receber': 100})

    def test_recebimento_exige_data_e_preserva_datas_historicas(self):
        doc = self.documento()
        url = reverse('atualizar_pagamento_documento', args=[doc.pk])
        self.assertEqual(self.client.post(url, {'situacao_pagamento': 'recebido'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'situacao_pagamento': 'recebido', 'data_pagamento': '2024-06-09'}).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.data_pagamento, date(2024, 6, 9))
        self.assertEqual(doc.data_emissao, date(2024, 5, 10))
        self.assertEqual(doc.data_vencimento, date(2024, 6, 10))
        self.client.post(url, {'situacao_pagamento': 'a_receber'})
        doc.refresh_from_db()
        self.assertIsNone(doc.data_pagamento)

    def test_detalhamento_nao_altera_valores_situacao_ou_datas(self):
        doc = self.documento()
        response = self.client.post(reverse('editar_detalhamento_documento', args=[doc.pk]), {
            'descricao': 'Lavagens da unidade Campinas', 'observacoes': 'Referência: maio de 2024.',
            'centro_custo': 'Operação', 'unidade': 'Campinas', 'valor': '999.00', 'data_emissao': '2026-09-30',
        })
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.valor, 100)
        self.assertEqual(doc.data_emissao, date(2024, 5, 10))
        self.assertEqual(doc.situacao_pagamento, 'a_receber')
        self.assertEqual(doc.observacoes, 'Referência: maio de 2024.')

    def test_upload_foto_financeira(self):
        photo = SimpleUploadedFile('pix.jpg', b'\xff\xd8\xff' + b'x' * 20, content_type='image/jpeg')
        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'recibo', 'numero_documento': 'PIX-1', 'descricao': 'Reembolso',
            'valor': '40.00', 'situacao_pagamento': 'pago', 'data_pagamento': '2024-08-02', 'arquivo_pdf': photo,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DocumentoFinanceiro.objects.get().arquivo.name.endswith('.jpg'))

    def test_edita_acervo_sem_trocar_arquivo_hash_vinculo_e_busca_observacao(self):
        arquivo = ArquivoImportado.objects.create(categoria='documento_financeiro', area='geral',
            nome_original='pix.jpg', arquivo='acervo/pix.jpg', sha256='a' * 64, status='revisar')
        response = self.client.post(reverse('editar_detalhamento_arquivo', args=[arquivo.pk]), {
            'area': 'financeiro', 'categoria': 'documento_financeiro', 'subcategoria': 'comprovante',
            'descricao': 'Compra de material', 'observacoes': 'Parafusos e ferramentas', 'data_documento': '2024-08-02',
        })
        self.assertEqual(response.status_code, 302)
        arquivo.refresh_from_db()
        self.assertEqual(arquivo.sha256, 'a' * 64)
        self.assertEqual(arquivo.arquivo.name, 'acervo/pix.jpg')
        self.assertEqual(arquivo.status, 'revisar')
        self.assertEqual(arquivo.metadados['origem_data_documento'], 'revisao_manual')
        self.assertEqual(arquivo.data_documento, date(2024, 8, 2))
        response = self.client.get(reverse('arquivo_central'), {'q': 'Parafusos', 'area': 'financeiro'})
        self.assertContains(response, 'pix.jpg')

    def test_usuario_sem_permissao_nao_edita(self):
        doc = self.documento()
        user = User.objects.create_user('leitor', password='teste')
        from financeiro.views import editar_detalhamento_documento
        request = RequestFactory().post('/', {'descricao': 'Alterado'})
        request.user = user
        with self.assertRaises(PermissionDenied):
            editar_detalhamento_documento(request, doc.pk)

    def test_data_de_copia_nao_vira_data_do_documento(self):
        origem = SimpleNamespace(modificado_em=datetime(2026, 9, 30, tzinfo=timezone.utc))
        self.assertEqual(_data_documento({}, origem), (None, ''))
        self.assertEqual(_data_documento({'data_emissao': '2024-01-02'}, origem), (date(2024, 1, 2), 'data_emissao'))

    @patch('core.services.processamento_storage._vincular_financeiro')
    @patch('core.services.processamento_storage._vincular_pagamento')
    @patch('core.services.processamento_storage.extrair_documento')
    def test_reprocessar_historico_preserva_revisao_manual_sem_gerar_pagamento(self, extrair, pagamento, financeiro):
        from core.services.processamento_storage import processar_arquivo
        key = default_storage.save('historico.jpg', ContentFile(b'conteudo'))
        arquivo = ArquivoImportado.objects.create(categoria='documento_financeiro', area='financeiro',
            nome_original='historico.jpg', arquivo=key, sha256='c' * 64,
            data_documento=date(2024, 1, 2), metadados={'somente_acervo': True, 'origem_data_documento': 'revisao_manual'})
        extrair.return_value = ('texto', {'data_emissao': '2026-09-30'}, 'teste')
        processar_arquivo(arquivo, usar_ocr=False, forcar=True)
        arquivo.refresh_from_db()
        self.assertEqual(arquivo.data_documento, date(2024, 1, 2))
        self.assertEqual(arquivo.metadados['origem_data_documento'], 'revisao_manual')
        pagamento.assert_not_called()
        financeiro.assert_not_called()
