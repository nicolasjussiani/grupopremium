from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from admissional.forms import PagamentoColaboradorForm
from admissional.models import Colaborador, PagamentoColaborador


class PagamentosColaboradoresTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_folha',
            email='admin@example.com',
            password='senha-forte',
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.colaborador = Colaborador.objects.create(
            nome='Fulano de Tal',
            salario=Decimal('2000.00'),
            vale_transporte_semanal=Decimal('80.00'),
        )

    def dados_pagamento(self, **overrides):
        dados = {
            'colaborador': self.colaborador.pk,
            'tipo': 'salario',
            'competencia': '2026-09-01',
            'valor': '2000,00',
            'data_vencimento': '2026-09-05',
            'status': 'pendente',
            'data_pagamento': '',
            'observacao': '',
        }
        dados.update(overrides)
        return dados

    def test_lista_exige_autenticacao(self):
        self.client.logout()
        response = self.client.get(reverse('lista_pagamentos_colaboradores'))
        self.assertEqual(response.status_code, 302)

    def test_cadastra_pagamento_pendente(self):
        response = self.client.post(
            reverse('novo_pagamento_colaborador'),
            self.dados_pagamento(),
        )

        self.assertRedirects(response, reverse('lista_pagamentos_colaboradores'))
        pagamento = PagamentoColaborador.objects.get()
        self.assertEqual(pagamento.valor, Decimal('2000.00'))
        self.assertEqual(pagamento.status, 'pendente')
        self.assertIsNone(pagamento.data_pagamento)
        self.assertEqual(pagamento.criado_por, self.user)

    def test_pagamento_pago_exige_data(self):
        form = PagamentoColaboradorForm(data=self.dados_pagamento(status='pago'))

        self.assertFalse(form.is_valid())
        self.assertIn('data_pagamento', form.errors)

    def test_pagamento_rejeita_valor_zerado(self):
        form = PagamentoColaboradorForm(data=self.dados_pagamento(valor='0,00'))

        self.assertFalse(form.is_valid())
        self.assertIn('valor', form.errors)

    def test_atalho_do_colaborador_preenche_tipo_e_valor_de_referencia(self):
        response = self.client.get(reverse('novo_pagamento_colaborador'), {
            'colaborador': self.colaborador.pk,
            'tipo': 'vale_transporte',
        })

        form = response.context['form']
        self.assertEqual(form.initial['colaborador'], str(self.colaborador.pk))
        self.assertEqual(form.initial['tipo'], 'vale_transporte')
        self.assertEqual(form.initial['valor'], Decimal('80.00'))

    def test_pagamento_pendente_remove_data_de_pagamento(self):
        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            status='pendente',
            data_pagamento='2026-09-04',
        ))

        self.assertTrue(form.is_valid(), form.errors)
        pagamento = form.save()
        self.assertIsNone(pagamento.data_pagamento)

    def test_permite_parcelas_na_mesma_competencia(self):
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 5),
        )
        form = PagamentoColaboradorForm(data=self.dados_pagamento())

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(PagamentoColaborador.objects.count(), 2)

    def test_marca_pagamento_pendente_como_pago_hoje(self):
        pagamento = PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='vale_transporte',
            competencia=date(2026, 9, 14),
            valor=Decimal('80.00'),
            data_vencimento=date(2026, 9, 14),
        )

        response = self.client.post(
            reverse('marcar_pagamento_como_pago', args=[pagamento.pk])
        )

        self.assertRedirects(response, reverse('lista_pagamentos_colaboradores'))
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')
        self.assertEqual(pagamento.data_pagamento, timezone.localdate())

    def test_confirmacao_de_pagamento_nao_aceita_get(self):
        pagamento = PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 8, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 8, 5),
        )

        response = self.client.get(
            reverse('marcar_pagamento_como_pago', args=[pagamento.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_lista_filtra_situacao(self):
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 5),
        )
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='vale_transporte',
            competencia=date(2026, 9, 8),
            valor=Decimal('80.00'),
            data_vencimento=date(2026, 9, 8),
            status='pago',
            data_pagamento=date(2026, 9, 8),
        )

        response = self.client.get(
            reverse('lista_pagamentos_colaboradores'), {'status': 'pendente'}
        )

        self.assertContains(response, '2000,00')
        self.assertNotContains(response, '80,00')
