from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import PerfilUsuario
from financeiro.models import AuditoriaItem, DocumentoFinanceiro, LancamentoERP


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
        self.assertNotContains(
            response, 'name="arquivo_pdf" accept="application/pdf" class="form-control" required'
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
