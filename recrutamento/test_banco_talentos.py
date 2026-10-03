from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import PerfilUsuario
from recrutamento.models import Talento


class BancoTalentosTests(TestCase):
    def setUp(self):
        usuario = User.objects.create_user('rh-talentos', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=usuario, perfil='rh')
        self.client.force_login(usuario)
        self.url = reverse('adicionar_talento')

    def test_cadastra_varias_pessoas_sem_email_e_cpf(self):
        for indice, opcionais in enumerate([
            {},
            {'email': '', 'cpf_cnpj': ''},
            {'email': '   ', 'cpf_cnpj': '   '},
        ]):
            with self.subTest(opcionais=opcionais):
                nome = f'Talento sem documentos {indice}'
                response = self.client.post(self.url, {
                    'nome': nome,
                    'telefone': '11999999999',
                    **opcionais,
                })

                self.assertRedirects(response, reverse('banco_talentos'))
                talento = Talento.objects.get(nome=nome)
                self.assertIsNone(talento.email)
                self.assertEqual(talento.cpf_cnpj, '')

        self.assertEqual(Talento.objects.count(), 3)

    def test_preserva_email_e_cpf_quando_informados(self):
        response = self.client.post(self.url, {
            'nome': 'Talento com documentos',
            'telefone': '11999999999',
            'email': ' talento@example.com ',
            'cpf_cnpj': ' 123.456.789-00 ',
        })

        self.assertRedirects(response, reverse('banco_talentos'))
        talento = Talento.objects.get()
        self.assertEqual(talento.email, 'talento@example.com')
        self.assertEqual(talento.cpf_cnpj, '123.456.789-00')

    def test_nao_duplica_email_informado(self):
        dados = {
            'nome': 'Talento com email',
            'telefone': '11999999999',
            'email': 'talento@example.com',
        }
        self.assertRedirects(self.client.post(self.url, dados), reverse('banco_talentos'))

        response = self.client.post(self.url, {**dados, 'nome': 'Outra pessoa'}, follow=True)

        self.assertContains(response, 'Já existe um talento com o e-mail')
        self.assertEqual(Talento.objects.count(), 1)

    def test_rejeita_email_invalido_quando_informado(self):
        response = self.client.post(self.url, {
            'nome': 'Talento com email inválido',
            'telefone': '11999999999',
            'email': 'email-invalido',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Talento.objects.exists())

    def test_nome_e_telefone_continuam_obrigatorios(self):
        for campo, mensagem in [('nome', 'Nome é obrigatório.'), ('telefone', 'Telefone é obrigatório.')]:
            with self.subTest(campo=campo):
                dados = {'nome': 'Talento incompleto', 'telefone': '11999999999'}
                dados[campo] = ''
                response = self.client.post(self.url, dados)

                self.assertContains(response, mensagem)
                self.assertFalse(Talento.objects.exists())
