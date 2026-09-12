from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Colaborador


class ListaColaboradoresContratoTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='consulta_colaboradores',
            email='consulta@example.com',
            password='senha-teste',
        )
        self.client.force_login(self.user)

    def test_exibe_contrato_no_lugar_da_marca(self):
        Colaborador.objects.create(
            nome='Colaborador Teste',
            cpf='12345678901',
            cargo='Lavador',
            unidade='Bauru',
            contrato='MOVIDA SN',
            marca='eco_premium',
            data_admissao=date(2026, 3, 6),
            status='ativo',
        )

        response = self.client.get(reverse('lista_colaboradores'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<th>Contrato</th>', html=True)
        self.assertContains(response, 'MOVIDA SN')
        self.assertNotContains(response, '<th>Marca</th>', html=True)
        self.assertNotContains(response, 'Eco Premium')

    def test_indica_quando_contrato_nao_foi_informado(self):
        Colaborador.objects.create(
            nome='Colaborador Sem Contrato',
            cpf='10987654321',
            cargo='Auxiliar',
            unidade='Campinas',
            contrato='',
            data_admissao=date(2026, 4, 10),
            status='ativo',
        )

        response = self.client.get(reverse('lista_colaboradores'))

        self.assertContains(response, 'Não informado')
