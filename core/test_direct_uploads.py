from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse

from core.direct_uploads import TOKEN_SALT, verify_direct_upload


class DirectUploadEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('upload-admin', 'admin@example.com', 'senha')

    @override_settings(SUPABASE_S3_ENDPOINT_URL='https://example.supabase.co/storage/v1/s3')
    @patch('core.views_upload.create_direct_upload')
    def test_retorna_url_temporaria_para_usuario_autorizado(self, create_upload):
        create_upload.return_value = ('https://storage/upload', 'curriculos/a.pdf', 'token')
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('presign_upload'),
            data='{"field":"curriculo_pdf","filename":"cv.pdf","content_type":"application/pdf","size":100}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['token'], 'token')

    def test_exige_autenticacao(self):
        response = self.client.post(reverse('presign_upload'), data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 302)


class DirectUploadTokenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('uploader', password='senha')
        self.key = 'curriculos/teste.pdf'
        default_storage.save(self.key, ContentFile(b'%PDF-conteudo'))

    def tearDown(self):
        default_storage.delete(self.key)

    def test_valida_arquivo_armazenado_e_token_do_usuario(self):
        payload = {
            'uid': self.user.pk,
            'field': 'curriculo_pdf',
            'key': self.key,
            'size': len(b'%PDF-conteudo'),
            'content_type': 'application/pdf',
        }
        token = signing.dumps(payload, salt=TOKEN_SALT, compress=True)
        request = SimpleNamespace(
            user=self.user,
            POST={'direct_upload_curriculo_pdf': token},
        )
        self.assertEqual(verify_direct_upload(request, 'curriculo_pdf'), self.key)

    def test_rejeita_token_adulterado(self):
        request = SimpleNamespace(
            user=self.user,
            POST={'direct_upload_curriculo_pdf': 'token-invalido'},
        )
        with self.assertRaises(ValidationError):
            verify_direct_upload(request, 'curriculo_pdf')
