from django.test import TestCase
from admissional.forms import ColaboradorForm
from admissional.models import Colaborador


class PixCadastroTests(TestCase):
    def test_novo_cadastro_rejeita_pix_ausente_vazio_ou_so_espacos(self):
        for value in (None, '', '   '):
            data = {'nome': 'Pessoa de teste', 'data_admissao': '2026-09-28'}
            if value is not None:
                data['chave_pix'] = value
            form = ColaboradorForm(data=data)
            self.assertFalse(form.is_valid())
            self.assertEqual(form.errors['chave_pix'], ['Informe a chave PIX do colaborador.'])
            self.assertIn('required', str(form['chave_pix']))
        self.assertFalse(Colaborador.objects.exists())

    def test_novo_cadastro_persiste_pix(self):
        form = ColaboradorForm(data={'nome': 'Pessoa', 'data_admissao': '2026-09-28',
                                     'chave_pix': ' pessoa@example.com '})
        self.assertTrue(form.is_valid(), form.errors)
        pessoa = form.save()
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.chave_pix, 'pessoa@example.com')

    def test_edicao_de_cadastro_antigo_nao_exige_pix_retroativamente(self):
        pessoa = Colaborador.objects.create(nome='Cadastro antigo')
        form = ColaboradorForm(data={'nome': 'Nome corrigido'}, instance=pessoa)
        self.assertTrue(form.is_valid(), form.errors)
