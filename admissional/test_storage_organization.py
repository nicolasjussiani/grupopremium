from datetime import date

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase

from compras.models import Material
from financeiro.models import DocumentoFinanceiro
from manutencao.models import Ativo, RegistroManutencao
from recrutamento.models import Candidato, Talento
from sesmet.models import EquipamentoProtecao

from core.storage_organization import (
    canonical_prefix,
    iter_storage_files,
    orphan_quarantine_key,
)
from .models import Colaborador, DocumentoAdmissional


class ColaboradorStorageOrganizationTests(TestCase):
    def setUp(self):
        self.source_names = []
        self.destination_names = []

    def tearDown(self):
        for name in self.source_names + self.destination_names:
            default_storage.delete(name)

    def _colaborador(self):
        return Colaborador.objects.create(
            nome='Pessoa Teste',
            cpf='123.456.789-10',
            email='pessoa@example.com',
            cargo='Analista',
            unidade='Matriz',
            data_admissao=date.today(),
        )

    def test_anexo_e_movido_para_pasta_do_colaborador_e_do_tipo(self):
        colaborador = self._colaborador()
        source = default_storage.save(
            'colaboradores/docs/documento-original.pdf',
            ContentFile(b'%PDF-documento'),
        )
        self.source_names.append(source)

        colaborador.anexo_cpf.name = source
        colaborador.save(update_fields=['anexo_cpf'])
        colaborador.refresh_from_db()
        self.destination_names.append(colaborador.anexo_cpf.name)

        self.assertTrue(
            colaborador.anexo_cpf.name.startswith(
                f'admissional/colaboradores/{colaborador.pk}/documentos/anexo_cpf/'
            )
        )
        self.assertTrue(default_storage.exists(colaborador.anexo_cpf.name))

    def test_organizacao_e_idempotente(self):
        colaborador = self._colaborador()
        source = default_storage.save(
            'colaboradores/docs/documento-original.pdf',
            ContentFile(b'%PDF-documento'),
        )
        self.source_names.append(source)
        colaborador.anexo_rg.name = source
        colaborador.save(update_fields=['anexo_rg'])
        first_name = colaborador.anexo_rg.name
        self.destination_names.append(first_name)

        colaborador.save(update_fields=['anexo_rg'])

        self.assertEqual(colaborador.anexo_rg.name, first_name)

    def test_todos_os_modelos_tem_caminho_especifico(self):
        cases = (
            (
                DocumentoAdmissional(pk=13, admissao_id=2, tipo='rg'),
                'arquivo_nuvem',
                'admissional/admissoes/2/documentos/rg/13/',
            ),
            (
                Candidato(pk=7, vaga_id=8),
                'arquivo',
                'recrutamento/vagas/8/candidatos/7/curriculo/',
            ),
            (
                Talento(pk=12),
                'arquivo',
                'recrutamento/talentos/12/curriculo/',
            ),
            (
                DocumentoFinanceiro(
                    pk=9, tipo='nota_fiscal', data_emissao=date(2026, 9, 9)
                ),
                'arquivo',
                'financeiro/documentos/2026/09/9/nota_fiscal/',
            ),
            (
                Ativo(pk=10),
                'foto',
                'manutencao/ativos/10/cadastro/foto/',
            ),
            (
                RegistroManutencao(pk=11, ativo_id=10),
                'foto_equipamento',
                'manutencao/ativos/10/registros/11/foto/',
            ),
            (
                Material(pk=14),
                'foto',
                'compras/materiais/14/foto/',
            ),
            (
                EquipamentoProtecao(pk=15),
                'foto',
                'sesmet/epis/15/foto/',
            ),
        )
        for instance, field_name, expected in cases:
            with self.subTest(model=instance._meta.label):
                self.assertEqual(canonical_prefix(instance, field_name), expected)

    def test_orfao_recebe_caminho_de_quarentena_sem_nome_original(self):
        source = 'curriculos/Maria_CPF_12345678900.pdf'
        destination = orphan_quarantine_key(source)

        self.assertTrue(destination.startswith('_orfaos/legado/curriculos/'))
        self.assertTrue(destination.endswith('.pdf'))
        self.assertNotIn('Maria', destination)
        self.assertNotIn('12345678900', destination)

    def test_listagem_s3_usa_paginacao_e_ignora_pastas(self):
        class FakePaginator:
            def paginate(self, **kwargs):
                self.kwargs = kwargs
                return [
                    {'Contents': [
                        {'Key': 'financeiro/'},
                        {'Key': 'financeiro/documentos/1.pdf'},
                    ]},
                    {'Contents': [{'Key': 'financeiro/documentos/2.pdf'}]},
                ]

        class FakeClient:
            def __init__(self):
                self.paginator = FakePaginator()

            def get_paginator(self, operation):
                self.operation = operation
                return self.paginator

        class FakeMeta:
            def __init__(self):
                self.client = FakeClient()

        class FakeConnection:
            def __init__(self):
                self.meta = FakeMeta()

        class FakeStorage:
            bucket_name = 'arquivos'
            connection = FakeConnection()

        storage = FakeStorage()

        names = list(iter_storage_files(storage, 'financeiro'))

        self.assertEqual(names, [
            'financeiro/documentos/1.pdf',
            'financeiro/documentos/2.pdf',
        ])
        self.assertEqual(storage.connection.meta.client.operation, 'list_objects_v2')
        self.assertEqual(
            storage.connection.meta.client.paginator.kwargs,
            {'Bucket': 'arquivos', 'Prefix': 'financeiro/'},
        )
