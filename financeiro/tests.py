from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import PerfilUsuario
from financeiro.models import AuditoriaItem, DocumentoFinanceiro, LancamentoERP
from financeiro.services.ocr_service import extrair_dados_documento


class LeituraProvisoriaDocumentoTests(SimpleTestCase):
    @patch.dict('os.environ', {}, clear=True)
    def test_sem_chave_api_usa_modo_local(self):
        dados = extrair_dados_documento(b'\x89PNG\r\n\x1a\n', 'image/png')
        self.assertEqual(dados['_modo'], 'local')
        self.assertIn('chave da IA', dados['_aviso'])
        self.assertEqual(dados['produtos'], [])


class EntradaDocumentoOpcionalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('financeiro-opcional', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='financeiro')
        grupo, _ = Group.objects.get_or_create(name='Financeiro_Operador')
        self.user.groups.add(grupo)
        self.client.force_login(self.user)

    @staticmethod
    def _pdf():
        return SimpleUploadedFile(
            'documento.pdf', b'%PDF-1.4\nconteudo de teste', content_type='application/pdf'
        )

    def test_novo_documento_aceita_campos_complementares_vazios(self):
        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'nota_fiscal',
            'numero_documento': 'NF-OPCIONAL-001',
            'descricao': 'Documento aguardando complementacao',
            'valor': '125.50',
            'arquivo_pdf': self._pdf(),
        })

        self.assertEqual(response.status_code, 302)
        documento = DocumentoFinanceiro.objects.get(numero_documento='NF-OPCIONAL-001')
        self.assertEqual(documento.cnpj_emitente, '')
        self.assertEqual(documento.razao_social_emitente, '')
        self.assertEqual(documento.centro_custo, '')
        self.assertEqual(documento.unidade, '')
        self.assertIsNone(documento.data_emissao)
        self.assertIsNone(documento.data_vencimento)
        self.assertEqual(documento.auditoria.count(), len(AuditoriaItem.ITENS_CHECKLIST))

    def test_novo_documento_aceita_cadastro_sem_pdf(self):
        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'nota_fiscal',
            'numero_documento': 'NF-SEM-PDF-001',
            'descricao': 'Documento cadastrado sem anexo',
            'valor': '89.90',
        })

        self.assertEqual(response.status_code, 302)
        documento = DocumentoFinanceiro.objects.get(numero_documento='NF-SEM-PDF-001')
        self.assertFalse(documento.arquivo)

    def test_novo_documento_rejeita_imagem_no_campo_pdf(self):
        imagem = SimpleUploadedFile(
            'documento.png', b'\x89PNG\r\n\x1a\nconteudo', content_type='image/png'
        )

        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'nota_fiscal',
            'numero_documento': 'NF-IMAGEM-001',
            'descricao': 'Arquivo com formato incorreto',
            'valor': '89.90',
            'arquivo_pdf': imagem,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Extensao de arquivo nao permitida.')
        self.assertFalse(
            DocumentoFinanceiro.objects.filter(numero_documento='NF-IMAGEM-001').exists()
        )

    def test_formulario_indica_campos_complementares_como_opcionais(self):
        response = self.client.get(reverse('entrada_documento'))

        self.assertContains(response, 'Obrigatórios somente')
        self.assertNotContains(
            response, 'name="cnpj_emitente" class="form-control" required'
        )
        self.assertNotContains(
            response, 'name="data_vencimento" class="form-control" required'
        )
        self.assertContains(response, 'inclusive o PDF')
        self.assertContains(response, 'Documento financeiro em PDF')
        self.assertContains(response, 'com até 50 MB')
        self.assertNotContains(
            response, 'name="arquivo_pdf" accept=".pdf,application/pdf" class="form-control" required'
        )

    def test_campo_pdf_aparece_antes_dos_dados_do_documento(self):
        response = self.client.get(reverse('entrada_documento'))
        conteudo = response.content.decode()

        self.assertLess(
            conteudo.index('name="arquivo_pdf"'),
            conteudo.index('name="tipo"'),
        )

    def test_centro_de_custo_pode_ser_informado_no_lancamento(self):
        documento = DocumentoFinanceiro.objects.create(
            tipo='nota_fiscal', numero_documento='NF-OPCIONAL-002',
            descricao='Documento sem classificacao inicial', valor='50.00',
            status='aprovado_lancamento',
        )

        response = self.client.post(reverse('lancar_erp', args=[documento.pk]), {
            'descricao': 'Lancamento classificado depois',
            'tipo': 'debito',
            'competencia': '2026-09-01',
            'centro_custo': 'ADM',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LancamentoERP.objects.get(documento=documento).centro_custo, 'ADM')
