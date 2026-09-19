from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import ArquivoImportado, PerfilUsuario
from core.services.assistente_provisorio import registrar_documento, responder_pergunta


class AssistenteProvisorioTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('operador-ai', password='senha-forte')
        PerfilUsuario.objects.create(usuario=self.user, perfil='operacional')
        self.client.force_login(self.user)

    def test_tela_e_pergunta_nao_criam_registros(self):
        response = self.client.get(reverse('assistente_erp'))
        self.assertEqual(response.status_code, 200)
        antes = ArquivoImportado.objects.count()
        response = self.client.post(reverse('assistente_erp'), {
            'acao': 'perguntar',
            'pergunta': 'Pode alterar e aprovar por mim?',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'nao altero')
        self.assertEqual(ArquivoImportado.objects.count(), antes)

    def test_perfil_sem_acesso_nao_recebe_indicador_financeiro(self):
        resposta = responder_pergunta(self.user, 'quantos pagamentos existem?')
        self.assertIn('restritos', resposta)

    def test_documento_fica_em_revisao_sem_criar_objeto_final(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            key = default_storage.save(
                '_temporarios/assistente/documentos/teste.pdf',
                ContentFile(b'%PDF-1.4\n% documento de teste'),
            )
            arquivo, criado = registrar_documento(
                self.user, key, 'pedido_teste.pdf', 'application/pdf', 'pedido'
            )
            self.assertTrue(criado)
            self.assertEqual(arquivo.status, 'revisar')
            self.assertEqual(arquivo.categoria, 'pedido')
            self.assertTrue(arquivo.metadados['origem_assistente'])
            self.assertEqual(Path(arquivo.arquivo.name).suffix, '.pdf')
