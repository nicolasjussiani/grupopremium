from datetime import date, timedelta
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

    def test_colaborador_inativo_nao_pode_receber_novo_pagamento(self):
        self.colaborador.status = 'inativo'
        self.colaborador.save(update_fields=['status'])

        form = PagamentoColaboradorForm(data=self.dados_pagamento())

        self.assertFalse(form.is_valid())
        self.assertIn('colaborador', form.errors)

    def test_lista_padrao_nao_exibe_pagamento_cancelado(self):
        hoje = timezone.localdate()
        pagamento = PagamentoColaborador.objects.create(
            colaborador=self.colaborador, tipo='salario', competencia=hoje,
            valor=Decimal('2000.00'), data_vencimento=hoje,
        )
        self.colaborador.status = 'inativo'
        self.colaborador.save(update_fields=['status'])

        response = self.client.get(reverse('lista_pagamentos_colaboradores'), {
            'data_inicio': hoje.isoformat(), 'data_fim': hoje.isoformat(),
        })

        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'cancelado')
        self.assertNotContains(response, self.colaborador.nome)

    def test_pagamento_pago_de_desligado_nao_entra_na_folha_nem_dashboard(self):
        hoje = timezone.localdate()
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=hoje.replace(day=1),
            valor=Decimal('2000.00'),
            data_vencimento=hoje,
            status='pago',
            data_pagamento=hoje,
        )
        self.colaborador.status = 'desligado'
        self.colaborador.save(update_fields=['status'])

        folha = self.client.get(reverse('lista_pagamentos_colaboradores'), {
            'data_inicio': hoje.replace(day=1).isoformat(),
            'data_fim': hoje.isoformat(),
        })
        financeiro = self.client.get(reverse('painel_financeiro'))

        self.assertNotContains(folha, self.colaborador.nome)
        self.assertEqual(financeiro.context['folha_mes_quantidade'], 0)
        self.assertEqual(financeiro.context['folha_mes_total'], 0)

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

    def test_vt_e_ajuda_de_custo_sao_normalizados_para_segunda_feira(self):
        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            tipo='vale_transporte',
            competencia='2026-09-10',
            competencia_fim='2026-09-30',
            data_vencimento='2026-09-12',
        ))

        self.assertTrue(form.is_valid(), form.errors)
        pagamento = form.save()
        self.assertEqual(pagamento.competencia, date(2026, 9, 7))
        self.assertEqual(pagamento.competencia_fim, date(2026, 9, 13))
        self.assertEqual(pagamento.data_vencimento, date(2026, 9, 7))
        self.assertTrue(pagamento.recorrente)

    def test_pagamento_realizado_de_vt_registra_segunda_da_semana(self):
        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            tipo='vale_transporte',
            competencia='2026-09-10',
            data_vencimento='2026-09-12',
            status='pago',
            data_pagamento='2026-09-12',
        ))

        self.assertTrue(form.is_valid(), form.errors)
        pagamento = form.save()
        self.assertEqual(pagamento.data_pagamento, date(2026, 9, 7))

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

    def test_rejeita_lancamento_exatamente_duplicado(self):
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 5),
        )
        form = PagamentoColaboradorForm(data=self.dados_pagamento())

        self.assertFalse(form.is_valid())
        self.assertEqual(PagamentoColaborador.objects.count(), 1)

    def test_rejeita_outro_salario_no_mesmo_vencimento(self):
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 5),
        )

        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            valor='400,00',
        ))

        self.assertFalse(form.is_valid())
        self.assertEqual(PagamentoColaborador.objects.count(), 1)

    def test_rejeita_dois_salarios_pagos_no_mesmo_dia(self):
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 8, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 8, 5),
            status='pago',
            data_pagamento=date(2026, 9, 10),
        )

        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            valor='400,00',
            data_vencimento='2026-09-06',
            status='pago',
            data_pagamento='2026-09-10',
        ))

        self.assertFalse(form.is_valid())
        self.assertEqual(PagamentoColaborador.objects.count(), 1)

    def test_rejeita_mesmo_valor_na_mesma_competencia_com_outro_vencimento(self):
        PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 10),
            status='pago',
            data_pagamento=date(2026, 9, 10),
        )

        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            data_vencimento='2026-09-30',
        ))

        self.assertFalse(form.is_valid())
        self.assertEqual(PagamentoColaborador.objects.count(), 1)

    def test_marca_vt_como_pago_na_segunda_da_semana(self):
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
        segunda = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        self.assertEqual(pagamento.data_pagamento, segunda)

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

    def test_lista_mostra_dias_trabalhados_do_periodo(self):
        PresencaDiaria.objects.create(
            colaborador=self.colaborador,
            data=date(2026, 9, 10),
            status='presente',
        )
        PresencaDiaria.objects.create(
            colaborador=self.colaborador,
            data=date(2026, 9, 11),
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
        self.assertEqual(response.context['pagamentos'][0].dias_trabalhados_exibicao, 1)
        self.assertContains(response, 'Dias trabalhados')
        self.assertNotContains(response, '>Faltas<')

    def test_lista_sem_presenca_mostra_nao_definido(self):
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

        self.assertContains(response, 'Não definido')

    def test_freelancer_calcula_total_por_dias_e_diaria(self):
        self.colaborador.categoria_trabalho = 'freelancer'
        self.colaborador.save(update_fields=['categoria_trabalho'])
        form = PagamentoColaboradorForm(data=self.dados_pagamento(
            tipo='freelancer',
            valor='',
            dias_trabalhados='7',
            valor_diaria='150,00',
            chave_pix='fulano@example.com',
        ))

        self.assertTrue(form.is_valid(), form.errors)
        pagamento = form.save()
        self.assertEqual(pagamento.valor, Decimal('1050.00'))
        self.assertEqual(pagamento.chave_pix, 'fulano@example.com')

    def test_retirar_pagamento_pendente_preserva_historico(self):
        pagamento = PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='vale_transporte',
            competencia=date(2026, 9, 7),
            valor=Decimal('80.00'),
            data_vencimento=date(2026, 9, 7),
            recorrente=True,
        )

        response = self.client.post(reverse('retirar_pagamento_folha', args=[pagamento.pk]))

        self.assertRedirects(response, reverse('lista_pagamentos_colaboradores'))
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'cancelado')
        self.assertFalse(pagamento.recorrente)
        self.assertTrue(PagamentoColaborador.objects.filter(pk=pagamento.pk).exists())

    def test_retirar_pagamento_nao_aceita_get(self):
        pagamento = PagamentoColaborador.objects.create(
            colaborador=self.colaborador,
            tipo='salario',
            competencia=date(2026, 9, 1),
            valor=Decimal('2000.00'),
            data_vencimento=date(2026, 9, 5),
        )

        response = self.client.get(reverse('retirar_pagamento_folha', args=[pagamento.pk]))

        self.assertEqual(response.status_code, 405)

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
