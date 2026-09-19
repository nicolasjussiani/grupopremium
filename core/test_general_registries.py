from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.models import Fornecedor, Unidade


class CadastrosGeraisTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('usuario-comum', password='senha-forte-123')
        self.client.force_login(self.user)

    def test_usuario_comum_cadastra_fornecedor_com_codigo_automatico(self):
        response = self.client.post(reverse('novo_fornecedor'), {
            'razao_social': 'Fornecedor Exemplo Ltda',
            'nome_fantasia': 'Fornecedor Exemplo',
            'cnpj': '12.345.678/0001-90',
            'contato': 'Pessoa de contato',
            'telefone': '11999999999',
            'email': 'compras@example.com',
            'observacoes': '',
            'ativo': 'on',
        })

        self.assertRedirects(response, reverse('cadastros_gerais'))
        fornecedor = Fornecedor.objects.get()
        self.assertEqual(fornecedor.codigo, f'FOR-{fornecedor.pk:06d}')
        self.assertEqual(fornecedor.criado_por, self.user)

    def test_usuario_comum_cadastra_unidade_com_codigo_automatico(self):
        response = self.client.post(reverse('nova_unidade'), {
            'nome': 'Filial Santos',
            'cidade': 'Santos',
            'estado': 'sp',
            'endereco': 'Avenida Exemplo, 100',
            'responsavel': 'Responsável Local',
            'telefone': '',
            'ativo': 'on',
        })

        self.assertRedirects(response, reverse('cadastros_gerais'))
        unidade = Unidade.objects.get(nome='Filial Santos')
        self.assertEqual(unidade.codigo, f'UNI-{unidade.pk:06d}')
        self.assertEqual(unidade.estado, 'SP')

    def test_opcoes_ativas_aparecem_nos_formularios_existentes(self):
        Fornecedor.objects.create(razao_social='Fornecedor Integrado', ativo=True)
        Unidade.objects.create(nome='Unidade Integrada', ativo=True)
        cache.clear()

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'id="fornecedoresCadastrados"')
        self.assertContains(response, 'Fornecedor Integrado')
        self.assertContains(response, 'id="unidadesCadastradas"')
        self.assertContains(response, 'Unidade Integrada')
        self.assertContains(response, "input[name=\"fornecedor\"]")

    def test_paginas_exigem_login(self):
        self.client.logout()
        for route in ('cadastros_gerais', 'novo_fornecedor', 'nova_unidade'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)
