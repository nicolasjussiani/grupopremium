from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from admissional.forms import PagamentoColaboradorForm
from admissional.models import Colaborador, PagamentoColaborador, PresencaDiaria
from core.models import PerfilUsuario


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
            'competencia_fim': '2026-09-30',
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

    def test_usuario_financeiro_acessa_folha_integrada(self):
        financeiro = User.objects.create_user('financeiro_folha', password='senha-forte')
        PerfilUsuario.objects.create(usuario=financeiro, perfil='financeiro')
        self.client.force_login(financeiro)

        response = self.client.get(reverse('lista_pagamentos_colaboradores'))

        self.assertEqual(response.status_code, 200)

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

    def test_pagamento_rejeita_ajuda_de_custo_para_clt(self):
        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            tipo='ajuda_custo',
        ))

        self.assertFalse(form.is_valid())
        self.assertIn('tipo', form.errors)

    def test_pagamento_rejeita_vale_transporte_para_pj(self):
        self.colaborador.tipo_contrato = 'pj'
        self.colaborador.save(update_fields=['tipo_contrato'])
        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            tipo='vale_transporte',
        ))

        self.assertFalse(form.is_valid())
        self.assertIn('tipo', form.errors)

    def test_pagamento_aceita_ajuda_de_custo_para_pj(self):
        self.colaborador.tipo_contrato = 'pj'
        self.colaborador.save(update_fields=['tipo_contrato'])
        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            tipo='ajuda_custo',
        ))

        self.assertTrue(form.is_valid(), form.errors)

    def test_modelo_rejeita_vale_transporte_para_pj_fora_do_formulario(self):
        self.colaborador.tipo_contrato = 'pj'
        self.colaborador.save(update_fields=['tipo_contrato'])
        pagamento = PagamentoColaborador(
            colaborador=self.colaborador,
            tipo='vale_transporte',
            competencia=date(2026, 9, 1),
            valor=Decimal('80.00'),
            data_vencimento=date(2026, 9, 5),
        )

        with self.assertRaises(ValidationError):
            pagamento.full_clean()

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

    def test_pagamento_recorrente_gera_proxima_semana_uma_vez(self):
        pagamento = PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='vale_transporte',
            competencia=date(2026, 9, 14),
            competencia_fim=date(2026, 9, 20),
            valor=Decimal('80.00'),
            data_vencimento=date(2026, 9, 14),
            recorrente=True,
        )

        self.client.post(reverse('marcar_pagamento_como_pago', args=[pagamento.pk]))
        self.client.post(reverse('marcar_pagamento_como_pago', args=[pagamento.pk]))

        proximo = PagamentoColaborador.objects.get(competencia=date(2026, 9, 21))
        self.assertEqual(proximo.competencia_fim, date(2026, 9, 27))
        self.assertEqual(proximo.status, 'pendente')
        self.assertTrue(proximo.recorrente)

    def test_lista_mostra_faltas_do_periodo(self):
        PresencaDiaria.objects.create(
            colaborador=self.colaborador,
            data=date(2026, 9, 10),
            status='falta',
        )
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 5),
        )

        response = self.client.get(reverse('lista_pagamentos_colaboradores'), {
            'data_inicio': '2026-09-01', 'data_fim': '2026-09-30',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pagamentos'][0].faltas_periodo, 1)

    def test_visao_de_beneficios_exclui_salario(self):
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='vale_transporte',
            competencia=date(2026, 9, 14),
            valor=Decimal('80.00'),
            data_vencimento=date(2026, 9, 14),
        )
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 5),
        )

        response = self.client.get(reverse('visao_beneficios_colaboradores'), {
            'data_inicio': '2026-09-01', 'data_fim': '2026-09-30',
        })

        self.assertContains(response, '80,00')
        self.assertNotContains(response, '2.000,00')
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


class PresencaNaoDefinidaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin_presenca', password='senha-forte')
        self.client = Client()
        self.client.force_login(self.user)
        self.colaborador = Colaborador.objects.create(nome='Sem marcação', status='ativo')

    def test_lista_sem_registro_aparece_como_nao_definido(self):
        response = self.client.get(reverse('controle_presenca'), {
            'data': '2026-09-18',
        })

        self.assertEqual(response.context['presencas'][0].status, 'indefinido')
        self.assertEqual(response.context['total_nao_definidos'], 1)
        self.assertContains(response, 'Não definido')

    def test_exportacao_inclui_colaborador_sem_marcacao(self):
        response = self.client.get(reverse('exportar_presenca_csv'), {
            'data': '2026-09-18',
        })

        conteudo = response.content.decode()
        self.assertIn('Sem marcação', conteudo)
        self.assertIn('Não definido', conteudo)
