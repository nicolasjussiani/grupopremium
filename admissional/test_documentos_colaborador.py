from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from admissional.forms import ColaboradorForm
from admissional.models import Colaborador, DocumentoColaborador
from core.models import PerfilUsuario


class DocumentoColaboradorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('rh-documentos', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=cls.user, perfil='rh')
        cls.colaborador = Colaborador.objects.create(
            nome='Colaborador documentos', cpf='987.654.321-00', cargo='Motorista',
            unidade='Matriz', data_admissao=date.today(),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_email_opcional_e_pis_ctps_fora_do_formulario(self):
        form = ColaboradorForm(data={
            'nome': 'Pessoa sem email', 'cpf': '111.222.333-44', 'email': '',
            'tipo_contrato': 'clt', 'cargo': 'Auxiliar', 'unidade': 'Matriz',
            'marca': 'eco_premium', 'data_admissao': date.today(), 'status': 'ativo',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('pis_pasep', form.fields)
        self.assertNotIn('ctps', form.fields)
        self.assertNotIn('anexo_pis', form.fields)
        self.assertNotIn('anexo_ctps', form.fields)

    def test_anexa_contrato_em_pasta_do_colaborador(self):
        url = reverse('documentos_colaborador', args=[self.colaborador.pk])
        response = self.client.post(url, {
            'tipo': 'contrato',
            'descricao': 'Contrato principal',
            'arquivo_colaborador': SimpleUploadedFile(
                'contrato.pdf', b'%PDF-contrato', content_type='application/pdf'
            ),
        })
        self.assertRedirects(response, url)
        documento = DocumentoColaborador.objects.get()
        self.assertEqual(documento.tipo, 'contrato')
        self.assertTrue(documento.arquivo.name.startswith(
            f'admissional/colaboradores/{self.colaborador.pk}/documentos/contrato/'
        ))

    def test_ajuda_de_custo_exige_semana_de_referencia(self):
        response = self.client.post(
            reverse('documentos_colaborador', args=[self.colaborador.pk]),
            {
                'tipo': 'ajuda_custo',
                'arquivo_colaborador': SimpleUploadedFile(
                    'ajuda.pdf', b'%PDF-ajuda', content_type='application/pdf'
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'semana de referência')
        self.assertFalse(DocumentoColaborador.objects.exists())

    def test_exclusao_remove_registro(self):
        documento = DocumentoColaborador.objects.create(
            colaborador=self.colaborador, tipo='comprovante_servico',
            arquivo=SimpleUploadedFile(
                'servico.pdf', b'%PDF-servico', content_type='application/pdf'
            ), enviado_por=self.user,
        )
        response = self.client.post(reverse(
            'excluir_documento_colaborador', args=[self.colaborador.pk, documento.pk]
        ))
        self.assertRedirects(
            response, reverse('documentos_colaborador', args=[self.colaborador.pk])
        )
        self.assertFalse(DocumentoColaborador.objects.filter(pk=documento.pk).exists())
