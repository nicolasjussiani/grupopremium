from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from core.models import PerfilUsuario
from core.storage_organization import canonical_key
from .forms import ColaboradorForm
from .models import Colaborador


class CadastroPixTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('rh_pix')
        PerfilUsuario.objects.create(usuario=cls.user, perfil='rh')

    def setUp(self):
        self.client.force_login(self.user)

    def dados(self, **extras):
        return {
            'nome': 'Pessoa teste PIX', 'data_admissao': '2026-09-30',
            'anexo_cpf': SimpleUploadedFile('cpf.pdf', b'%PDF-teste', content_type='application/pdf'),
            **extras,
        }

    def test_rh_cadastra_e_edita_pix(self):
        response = self.client.post(reverse('novo_colaborador'), self.dados(chave_pix='rh@example.com'))
        self.assertEqual(response.status_code, 302)
        pessoa = Colaborador.objects.get()
        self.assertEqual(pessoa.chave_pix, 'rh@example.com')
        response = self.client.post(reverse('editar_colaborador', args=[pessoa.pk]), {
            'nome': pessoa.nome, 'data_admissao': '2026-09-30', 'chave_pix': '+5511999990000',
        })
        self.assertEqual(response.status_code, 302)
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.chave_pix, '+5511999990000')

    def test_pix_opcional_e_nao_inferido_do_cpf(self):
        form = ColaboradorForm(data={'data_admissao': '2026-09-30', 'cpf': '123.456.789-01'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().chave_pix, '')

    def test_pix_aparece_uma_vez_no_formulario(self):
        response = self.client.get(reverse('novo_colaborador'))
        self.assertContains(response, 'name="chave_pix"', count=1)

    def test_erro_de_validacao_preserva_pix(self):
        response = self.client.post(reverse('novo_colaborador'), {'chave_pix': 'rh@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rh@example.com')
        self.assertFalse(Colaborador.objects.exists())

    def test_caminho_de_todos_anexos_cabe_no_banco(self):
        pessoa = Colaborador(pk=100000)
        for campo in ColaboradorForm.DIRECT_UPLOAD_FIELDS:
            with self.subTest(campo=campo):
                self.assertLessEqual(len(canonical_key(pessoa, campo, 'imagem.jpeg')), pessoa._meta.get_field(campo).max_length)

    def test_falha_na_limpeza_apos_commit_nao_quebra_cadastro_salvo(self):
        with patch.object(default_storage, 'delete', side_effect=OSError('falha na limpeza')):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse('novo_colaborador'), self.dados(chave_pix='rh@example.com'))
        self.assertEqual(response.status_code, 302)
        pessoa = Colaborador.objects.get()
        self.assertTrue(default_storage.exists(pessoa.anexo_cpf.name))
        self.assertEqual(pessoa.chave_pix, 'rh@example.com')
