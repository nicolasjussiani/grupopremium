from io import StringIO

from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase

from recrutamento.models import Talento


class LegacyStorageMigrationTests(TestCase):
    def tearDown(self):
        for talento in Talento.objects.exclude(arquivo=''):
            if talento.arquivo:
                default_storage.delete(talento.arquivo.name)

    def test_migra_confere_e_limpa_binario_legado(self):
        talento = Talento.objects.create(
            nome='Talento legado', email='legado@example.com', telefone='11999999999',
            cidade='Sao Paulo', cpf_cnpj='123.456.789-00',
            arquivo_pdf=b'%PDF-conteudo-legado',
        )

        output = StringIO()
        call_command(
            'migrar_arquivos_legados', '--execute', '--limpar-legado', stdout=output,
        )

        talento.refresh_from_db()
        self.assertIsNone(talento.arquivo_pdf)
        self.assertTrue(talento.arquivo.name.startswith(
            f'recrutamento/talentos/{talento.pk}/curriculo/'
        ))
        self.assertTrue(default_storage.exists(talento.arquivo.name))
        self.assertIn('1 migrado(s), 1 limpo(s), 0 conflito(s)', output.getvalue())
