from datetime import date
from hashlib import sha256

from django.contrib.auth.models import User
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador
from core.direct_uploads import TOKEN_SALT
from core.models import ArquivoImportado
from core.views_upload import _can_upload


class ComprovantesPagamentoTest(TestCase):
    def test_confirmar_exige_comprovante_e_vincula_ao_pagamento(self):
        self.client.post(reverse('novo_pagamento_colaborador'), self.dados)
        pagamento = PagamentoColaborador.objects.get()
        url = reverse('marcar_pagamento_como_pago', args=[pagamento.pk])
        self.assertContains(self.client.get(url), 'Confirmar pagamento com comprovante')
        response = self.client.post(url)
        self.assertContains(response, 'Anexe um comprovante')
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertIsNone(pagamento.data_pagamento)
        response = self.client.post(url, {'direct_upload_comprovante_folha': self.token()})
        self.assertEqual(response.status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')
        self.assertEqual(pagamento.arquivos_importados.count(), 1)
        self.client.post(url)
        self.assertEqual(pagamento.arquivos_importados.count(), 1)

    def test_comprovante_ja_anexado_pode_ser_usado_na_confirmacao(self):
        self.client.post(reverse('novo_pagamento_colaborador'), {**self.dados, 'direct_upload_comprovante_folha': self.token()})
        pagamento = PagamentoColaborador.objects.get()
        response = self.client.post(reverse('marcar_pagamento_como_pago', args=[pagamento.pk]))
        self.assertEqual(response.status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')

    def test_novo_e_edicao_nao_permitam_confirmar_sem_comprovante(self):
        dados = {**self.dados, 'status': 'pago', 'data_pagamento': '2026-09-05'}
        self.assertContains(self.client.post(reverse('novo_pagamento_colaborador'), dados), 'Anexe um comprovante')
        self.assertFalse(PagamentoColaborador.objects.exists())
        self.client.post(reverse('novo_pagamento_colaborador'), self.dados)
        pagamento = PagamentoColaborador.objects.get()
        response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), dados)
        self.assertContains(response, 'Anexe um comprovante')
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')

    def setUp(self):
        self.user = User.objects.create_superuser('admin_comprovante')
        self.client.force_login(self.user)
        self.colaborador = Colaborador.objects.create(nome='Pessoa comprovante')
        self.dados = {
            'colaborador': self.colaborador.pk, 'tipo': 'salario',
            'competencia': '2026-09-01', 'competencia_fim': '2026-09-30',
            'valor': '2000,00', 'data_vencimento': '2026-09-05', 'status': 'pendente',
        }

    def token(self, content=b'%PDF-1.4 comprovante', uid=None):
        key = default_storage.save('_temporarios/admissional/pagamentos/comprovantes/test.pdf', ContentFile(content))
        return signing.dumps({'uid': uid or self.user.pk, 'field': 'comprovante_folha',
                              'key': key, 'size': len(content), 'content_type': 'application/pdf'}, salt=TOKEN_SALT)

    def test_upload_direto_vincula_arquivo_sem_marcar_como_pago(self):
        response = self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'direct_upload_comprovante_folha': self.token(),
            'direct_upload_comprovante_folha_original_name': 'Recibo.pdf',
        })
        self.assertEqual(response.status_code, 302)
        pagamento = PagamentoColaborador.objects.get()
        arquivo = ArquivoImportado.objects.get()
        self.assertEqual(arquivo.content_object, pagamento)
        self.assertEqual(arquivo.nome_original, 'Recibo.pdf')
        self.assertEqual(arquivo.sha256, sha256(b'%PDF-1.4 comprovante').hexdigest())
        self.assertTrue(arquivo.arquivo.name.startswith('arquivo_central/'))
        self.assertTrue(default_storage.exists(arquivo.arquivo.name))
        self.assertEqual(arquivo.area, 'financeiro')
        self.assertEqual(pagamento.status, 'pendente')
        self.assertEqual(self.client.get(reverse('baixar_arquivo_importado', args=[arquivo.pk])).status_code, 302)

    def test_edicao_acrescenta_e_exibe_todos_os_comprovantes(self):
        self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'comprovante_folha': SimpleUploadedFile('primeiro.pdf', b'%PDF-1.4 primeiro', content_type='application/pdf'),
        })
        pagamento = PagamentoColaborador.objects.get()
        response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
            **self.dados, 'direct_upload_comprovante_folha': self.token(b'%PDF-1.4 segundo'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(pagamento.arquivos_importados.count(), 2)
        lista = self.client.get(reverse('lista_pagamentos_colaboradores'), {'data_inicio': '2026-09-01', 'data_fim': '2026-09-30'})
        for arquivo in pagamento.arquivos_importados.all():
            self.assertContains(lista, reverse('baixar_arquivo_importado', args=[arquivo.pk]))

    def test_token_de_outro_usuario_nao_cria_pagamento(self):
        response = self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'direct_upload_comprovante_folha': self.token(uid=self.user.pk + 1),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PagamentoColaborador.objects.exists())
        self.assertFalse(ArquivoImportado.objects.exists())

    def test_comprovante_de_outro_pagamento_nao_e_reutilizado(self):
        token = self.token()
        self.client.post(reverse('novo_pagamento_colaborador'), {**self.dados, 'direct_upload_comprovante_folha': token})
        response = self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'competencia': '2026-10-01', 'competencia_fim': '2026-10-31',
            'data_vencimento': '2026-10-05', 'direct_upload_comprovante_folha': token,
        })
        self.assertContains(response, 'Este comprovante já está cadastrado')
        self.assertEqual(PagamentoColaborador.objects.count(), 1)
        self.assertEqual(ArquivoImportado.objects.count(), 1)

    def test_erro_no_formulario_preserva_token_e_upload_nao_autoriza_operacional(self):
        token = self.token()
        response = self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'valor': '', 'direct_upload_comprovante_folha': token,
            'direct_upload_comprovante_folha_original_name': 'recibo.pdf',
        })
        self.assertContains(response, token)
        self.assertFalse(PagamentoColaborador.objects.exists())
        user = User.objects.create_user('operacional_comprovante')
        self.assertFalse(_can_upload(user, 'comprovante_folha'))

    def test_rejeita_arquivo_corrompido(self):
        response = self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'direct_upload_comprovante_folha': self.token(b'nao e PDF'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PagamentoColaborador.objects.exists())
