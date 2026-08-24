from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
import datetime
from unittest.mock import patch

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
        PerfilUsuario.objects.create(user=self.user, perfil='rh')
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

    @patch('django.core.files.storage.FileSystemStorage.save')
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

        # Ao enviar um POST com arquivo, se cair no FileSystemStorage,
        # esperamos que o erro OSError propague (causando o 500).
        # Para que a view não quebre com 500, precisaríamos de um try/except na view.
        # Como a view atual não tem tratamento, o teste irá falhar com OSError, 
        # o que comprova que esta é uma das causas do Erro 500!
        with self.assertRaises(OSError) as contexto:
            self.client.post(self.url, data=data, format='multipart')
        
        self.assertIn('Read-only file system', str(contexto.exception))
        
        # Conclusão: Se este teste passa (ou seja, a exceção é levantada), 
        # está provado que tentar salvar arquivos em disco na Vercel derruba a aplicação com Erro 500.
