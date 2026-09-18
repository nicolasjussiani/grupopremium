from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador
from core.models import ArquivoImportado, OrigemArquivoImportado
from core.services.importacao_arquivo_central import (
    ImportadorArquivoCentral, classificar, extrair_beneficiario, extrair_data,
    extrair_valor,
    nome_seguro_storage,
    sha256_arquivo,
)


TEXTO_PIX = '''
Informações de Pagamento
03/08/2026 - 14:38
Pix realizado
Beneficiário final
LUCAS HENRIQUE BORGES DE OLIVEIRA
Valor do documento
R$ 87,50
ID da transação
E31872495202608031737ABCDEF
'''


class ExtracaoArquivoCentralTest(TestCase):
    def test_nome_do_storage_remove_acentos_sem_perder_extensao(self):
        self.assertEqual(
            nome_seguro_storage('NFS RIBEIRÃO - LOCAÇÃO MARÇO.pdf'),
            'NFS_RIBEIRAO_-_LOCACAO_MARCO.pdf',
        )

    def test_extrai_dados_do_comprovante_pix(self):
        self.assertEqual(extrair_beneficiario(TEXTO_PIX), 'LUCAS HENRIQUE BORGES DE OLIVEIRA')
        self.assertEqual(str(extrair_valor(TEXTO_PIX)), '87.50')
        self.assertEqual(str(extrair_data(TEXTO_PIX, 'arquivo.pdf')), '2026-08-03')

    def test_classifica_vale_transporte(self):
        categoria, subcategoria = classificar(Path(
            'COMPROVANTE VT E ADIANTAMENTOS/BAURU/ANDRE ATAIDE/'
            'VALE TRANSPORTE SEMANAL - ANDRE ATAIDE - 01.06.26.pdf'
        ))
        self.assertEqual(categoria, 'pagamento_colaborador')
        self.assertEqual(subcategoria, 'vale_transporte')


class ImportacaoArquivoCentralTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('arquivo_admin', 'a@example.com', 'senha')
        self.colaborador = Colaborador.objects.create(
            nome='LUCAS HENRIQUE BORGES DE OLIVEIRA',
            unidade='AMERICANA',
        )

    @patch('core.services.importacao_arquivo_central.extrair_texto', return_value=TEXTO_PIX)
    def test_importa_comprovante_e_cria_pagamento_vinculado(self, _extrair):
        with TemporaryDirectory() as pasta:
            destino = Path(pasta) / 'COMPROVANTE VT E ADIANTAMENTOS' / 'AMERICANA' / 'LUCAS OLIVEIRA'
            destino.mkdir(parents=True)
            (destino / 'ADIANTAMENTO - LUCAS OLIVEIRA - 03.08.26.pdf').write_bytes(b'%PDF-teste')

            call_command('importar_arquivo_central', pasta, usuario=self.user.username)

        arquivo = ArquivoImportado.objects.get()
        pagamento = PagamentoColaborador.objects.get()
        self.assertEqual(arquivo.status, 'vinculado')
        self.assertEqual(arquivo.content_object, pagamento)
        self.assertEqual(pagamento.colaborador, self.colaborador)
        self.assertEqual(pagamento.tipo, 'adiantamento')
        self.assertEqual(str(pagamento.valor), '87.50')
        self.assertEqual(str(pagamento.data_pagamento), '2026-08-03')

    def test_deduplica_conteudo_e_preserva_duas_origens(self):
        with TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / 'NOTAS FISCAIS' / 'A').mkdir(parents=True)
            (raiz / 'NOTAS FISCAIS' / 'B').mkdir(parents=True)
            conteudo = b'<nota><nNF>123</nNF></nota>'
            (raiz / 'NOTAS FISCAIS' / 'A' / 'nota.xml').write_bytes(conteudo)
            (raiz / 'NOTAS FISCAIS' / 'B' / 'copia.xml').write_bytes(conteudo)

            call_command('importar_arquivo_central', pasta)

        self.assertEqual(ArquivoImportado.objects.count(), 1)
        self.assertEqual(OrigemArquivoImportado.objects.count(), 2)

    def test_retomada_trata_hash_inserido_depois_de_montar_o_indice(self):
        with TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            destino = raiz / 'NOTAS FISCAIS' / 'NFS LOCAÇÃO.pdf'
            destino.parent.mkdir(parents=True)
            destino.write_bytes(b'%PDF-conteudo-concorrente')
            importador = ImportadorArquivoCentral(raiz)
            digest = sha256_arquivo(destino)
            ArquivoImportado.objects.create(
                categoria='nota_fiscal',
                subcategoria='nota_fiscal',
                nome_original=destino.name,
                arquivo='arquivo_central/existente.pdf',
                sha256=digest,
                tamanho=destino.stat().st_size,
            )

            importador._importar(destino.resolve())

        self.assertEqual(ArquivoImportado.objects.filter(sha256=digest).count(), 1)
        self.assertEqual(OrigemArquivoImportado.objects.count(), 1)
        self.assertEqual(importador.contadores['duplicados'], 1)

    def test_tela_do_arquivo_central_exige_login(self):
        response = Client().get(reverse('arquivo_central'))
        self.assertEqual(response.status_code, 302)

    def test_superusuario_acessa_arquivo_central(self):
        cliente = Client()
        cliente.force_login(self.user)
        response = cliente.get(reverse('arquivo_central'))
        self.assertEqual(response.status_code, 200)

    def test_revisao_manual_vincula_pagamento(self):
        arquivo = ArquivoImportado.objects.create(
            categoria='pagamento_colaborador',
            subcategoria='adiantamento',
            nome_original='comprovante.pdf',
            arquivo=SimpleUploadedFile('comprovante.pdf', b'%PDF-teste'),
            sha256='a' * 64,
            tamanho=10,
            status='revisar',
            motivo_revisao='Colaborador não identificado com segurança.',
            metadados={
                'valor': '87,50',
                'data_pagamento': '2026-08-03',
                'identificador_transacao': 'TRANSACAO-MANUAL-1',
            },
        )
        cliente = Client()
        cliente.force_login(self.user)

        response = cliente.post(reverse('revisar_arquivo_importado', args=[arquivo.pk]), {
            'colaborador': self.colaborador.pk,
            'tipo': 'adiantamento',
            'competencia': '2026-08-03',
            'valor': '87,50',
            'data_pagamento': '2026-08-03',
            'observacao': 'Conferido manualmente',
        })

        self.assertRedirects(response, reverse('arquivo_central'))
        arquivo.refresh_from_db()
        self.assertEqual(arquivo.status, 'vinculado')
        self.assertEqual(arquivo.content_object.colaborador, self.colaborador)
