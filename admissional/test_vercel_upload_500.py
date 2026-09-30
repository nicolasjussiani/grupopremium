from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
import datetime
from unittest.mock import patch
from botocore.exceptions import ClientError, EndpointConnectionError
from admissional.models import Colaborador

class TestVercelUpload500(TestCase):
    """
    Teste automatizado focado em reproduzir e verificar
    o erro 500 causado por uploads no ambiente Serverless da Vercel.
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='test_rh', password='123')
        # Criamos o perfil para passar no middleware
        from core.models import PerfilUsuario
        PerfilUsuario.objects.create(usuario=self.user, perfil='rh')
        self.client.force_login(self.user)
        self.url = reverse('novo_colaborador')

    def _colaborador_data(self):
        return {
            'nome': 'João Teste',
            'cpf': '000.111.222-33',
            'email': 'joao@teste.com',
            'telefone': '11999999999',
            'cargo': 'Desenvolvedor',
            'unidade': 'SP-01',
            'data_admissao': datetime.date.today().isoformat(),
            'status': 'ativo',
            'tipo_contrato': 'clt',
            'marca': 'eco_premium',
        }

    @patch('django.core.files.storage.Storage.save')
    def test_erro_500_upload_read_only_vercel(self, mock_save):
        """
        Simula a Vercel (Sistema de Arquivos Read-Only) quando o S3 não está configurado.
        O FileSystemStorage lança OSError(30, 'Read-only file system').
        """
        # Configura o mock para disparar o mesmo erro da Vercel
        mock_save.side_effect = OSError(30, 'Read-only file system')

        fake_file = SimpleUploadedFile(
            'documento.pdf',
            b'%PDF-1.4\n...',
            content_type='application/pdf'
        )
        
        data = self._colaborador_data()
        data['anexo_cpf'] = fake_file

        # Falhas de armazenamento devem voltar ao formulario com uma mensagem.
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nao foi possivel armazenar os anexos')

    def test_falhas_s3_retornam_formulario_sem_cadastro_parcial(self):
        for error in (
            ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'privado'}}, 'PutObject'),
            EndpointConnectionError(endpoint_url='https://storage.invalid'),
        ):
            with self.subTest(error=type(error).__name__):
                data = self._colaborador_data()
                data['anexo_cpf'] = SimpleUploadedFile(
                    'cpf.pdf', b'%PDF-teste', content_type='application/pdf',
                )
                with patch('django.core.files.storage.Storage.save', side_effect=error):
                    response = self.client.post(self.url, data=data)
                self.assertContains(response, 'Nao foi possivel armazenar os anexos')
                self.assertNotContains(response, 'privado')
                self.assertFalse(Colaborador.objects.exists())

    def test_falha_ao_organizar_anexo_desfaz_insert_e_permite_consultas(self):
        data = self._colaborador_data()
        data['anexo_cpf'] = SimpleUploadedFile(
            'cpf.pdf', b'%PDF-teste', content_type='application/pdf',
        )
        error = ClientError({'Error': {'Code': 'AccessDenied'}}, 'CopyObject')
        with patch('core.storage_organization.copy_in_storage', side_effect=error):
            response = self.client.post(self.url, data=data)
        self.assertContains(response, 'Nao foi possivel armazenar os anexos')
        self.assertFalse(Colaborador.objects.exists())
        self.assertIsNone(response.context['form'].instance.pk)

    def test_falha_s3_na_edicao_preserva_cadastro(self):
        colaborador = Colaborador.objects.create(nome='Nome anterior')
        data = self._colaborador_data()
        data['anexo_cpf'] = SimpleUploadedFile(
            'cpf.pdf', b'%PDF-teste', content_type='application/pdf',
        )
        error = ClientError({'Error': {'Code': 'AccessDenied'}}, 'CopyObject')
        with patch('core.storage_organization.copy_in_storage', side_effect=error):
            response = self.client.post(reverse('editar_colaborador', args=[colaborador.pk]), data=data)
        self.assertContains(response, 'Nao foi possivel armazenar os anexos')
        colaborador.refresh_from_db()
        self.assertEqual(colaborador.nome, 'Nome anterior')
        self.assertFalse(colaborador.anexo_cpf)
