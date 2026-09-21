from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import ArquivoImportado, PerfilUsuario
from admissional.models import Colaborador, PagamentoColaborador
from core.services.assistente_provisorio import (
    _vincular_pagamento_automatico, registrar_documento, responder_pergunta,
)


class AssistenteProvisorioTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('operador-ai', password='senha-forte')
        PerfilUsuario.objects.create(usuario=self.user, perfil='operacional')
        self.client.force_login(self.user)

    def test_tela_e_pergunta_nao_criam_registros(self):
        response = self.client.get(reverse('assistente_erp'))
        self.assertRedirects(
            response,
            f'{reverse("dashboard")}#assistente-dashboard',
            fetch_redirect_response=False,
        )
        antes = ArquivoImportado.objects.count()
        response = self.client.post(reverse('dashboard'), {
            'acao': 'perguntar_ia',
            'pergunta': 'Pode alterar e aprovar por mim?',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'processado e arquivado automaticamente')
        self.assertEqual(ArquivoImportado.objects.count(), antes)

    def test_perfil_sem_acesso_nao_recebe_indicador_financeiro(self):
        resposta = responder_pergunta(self.user, 'quantos pagamentos existem?')
        self.assertIn('restritos', resposta)

    def test_documento_nao_financeiro_e_arquivado_sem_revisao(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            key = default_storage.save(
                '_temporarios/assistente/documentos/teste.pdf',
                ContentFile(b'%PDF-1.4\n% documento de teste'),
            )
            arquivo, criado = registrar_documento(
                self.user, key, 'pedido_teste.pdf', 'application/pdf', 'pedido'
            )
            self.assertTrue(criado)
            self.assertEqual(arquivo.status, 'arquivado')
            self.assertEqual(arquivo.categoria, 'pedido')
            self.assertTrue(arquivo.metadados['origem_assistente'])
            self.assertEqual(Path(arquivo.arquivo.name).suffix, '.pdf')

    def test_pagamento_completo_e_vinculado_sem_aprovacao(self):
        colaborador = Colaborador.objects.create(
            nome='Colaborador Automatico', cpf='123.456.789-10',
            cargo='Operador', unidade='Matriz', tipo_contrato='clt',
        )
        arquivo = ArquivoImportado.objects.create(
            categoria='pagamento_colaborador', subcategoria='salario',
            nome_original='salario.pdf', arquivo='arquivo-central/salario.pdf',
            sha256='a' * 64, tamanho=100, status='revisar', importado_por=self.user,
        )
        pagamento = _vincular_pagamento_automatico(
            arquivo, self.user, colaborador, Decimal('1500.00'),
            date(2026, 9, 5), 'tx-automatica-1',
        )
        arquivo.refresh_from_db()
        self.assertIsNotNone(pagamento)
        self.assertEqual(arquivo.status, 'vinculado')
        self.assertEqual(PagamentoColaborador.objects.count(), 1)
        self.assertEqual(pagamento.status, 'pago')

    def test_pagamento_incompleto_vira_erro_sem_fila_de_aprovacao(self):
        arquivo = ArquivoImportado.objects.create(
            categoria='pagamento_colaborador', subcategoria='outro',
            nome_original='ilegivel.pdf', arquivo='arquivo-central/ilegivel.pdf',
            sha256='b' * 64, tamanho=100, status='revisar', importado_por=self.user,
        )
        pagamento = _vincular_pagamento_automatico(
            arquivo, self.user, None, None, None, '',
        )
        arquivo.refresh_from_db()
        self.assertIsNone(pagamento)
        self.assertEqual(arquivo.status, 'erro')
