from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Colaborador, PagamentoColaborador
from .periodos_pagamentos import pagamentos_atuais, pagamentos_atrasados


class PeriodosPagamentosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser('periodos_ui')
        cls.pessoa = Colaborador.objects.create(nome='Pessoa de teste')
        cls.vt_antigo = cls.criar('vale_transporte', date(2026, 9, 21), 70)
        cls.vt_atual = cls.criar('vale_transporte', date(2026, 9, 28), 80)
        cls.vt_futuro = cls.criar('vale_transporte', date(2026, 10, 5), 90)
        cls.salario_antigo = cls.criar('salario', date(2026, 8, 5), 1000)
        cls.salario_atual = cls.criar('salario', date(2026, 9, 5), 2000)
        cls.salario_futuro = cls.criar('salario', date(2026, 10, 5), 3000)
        cls.cancelado = cls.criar('reembolso', date(2026, 8, 10), 50, status='cancelado')
        cls.pago = cls.criar('reembolso', date(2026, 8, 11), 60, status='pago', data_pagamento=date(2026, 8, 11))

    @classmethod
    def criar(cls, tipo, dia, valor, **kwargs):
        return PagamentoColaborador.objects.create(
            colaborador=cls.pessoa, tipo=tipo, competencia=dia,
            data_vencimento=dia, valor=valor, **kwargs,
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.clock = patch('django.utils.timezone.localdate', return_value=date(2026, 9, 30))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def ids(self, queryset):
        return set(queryset.values_list('pk', flat=True))

    def test_atual_separa_semana_e_mes_e_nao_inclui_futuros(self):
        self.assertEqual(self.ids(pagamentos_atuais(PagamentoColaborador.objects.all(), date(2026, 9, 30))), {
            self.vt_atual.pk, self.salario_atual.pk,
        })

    def test_atrasados_inclui_apenas_pendentes_de_periodos_encerrados(self):
        self.assertEqual(self.ids(pagamentos_atrasados(PagamentoColaborador.objects.all(), date(2026, 9, 30))), {
            self.vt_antigo.pk, self.salario_antigo.pk,
        })

    def test_virada_do_mes_mantem_semana_e_move_salario(self):
        self.assertEqual(self.ids(pagamentos_atuais(PagamentoColaborador.objects.all(), date(2026, 10, 1))), {
            self.vt_atual.pk, self.salario_futuro.pk,
        })
        self.assertIn(self.salario_atual.pk, self.ids(pagamentos_atrasados(PagamentoColaborador.objects.all(), date(2026, 10, 1))))

    def test_domingo_ainda_atual_e_segunda_move_vt_para_atrasados(self):
        self.assertIn(self.vt_atual.pk, self.ids(pagamentos_atuais(PagamentoColaborador.objects.all(), date(2026, 10, 4))))
        atuais = self.ids(pagamentos_atuais(PagamentoColaborador.objects.all(), date(2026, 10, 5)))
        self.assertNotIn(self.vt_atual.pk, atuais)
        self.assertIn(self.vt_futuro.pk, atuais)
        self.assertIn(self.vt_atual.pk, self.ids(pagamentos_atrasados(PagamentoColaborador.objects.all(), date(2026, 10, 5))))

    def test_virada_de_ano_semana_cruza_meses(self):
        vt = self.criar('vale_transporte', date(2026, 12, 28), 100)
        self.assertIn(vt.pk, self.ids(pagamentos_atuais(PagamentoColaborador.objects.all(), date(2027, 1, 1))))
        self.assertIn(vt.pk, self.ids(pagamentos_atrasados(PagamentoColaborador.objects.all(), date(2027, 1, 4))))

    def test_folha_padrao_e_painel_tem_mesmos_totais(self):
        folha = self.client.get(reverse('lista_pagamentos_colaboradores'))
        painel = self.client.get(reverse('painel_financeiro'))
        self.assertEqual(folha.context['visao'], 'atual')
        self.assertEqual(folha.context['total_pendente'], Decimal('2080'))
        self.assertEqual(painel.context['folha_mes_pendente'], folha.context['total_pendente'])
        self.assertEqual(painel.context['folha_atrasada_total'], Decimal('1070'))
        self.assertEqual(folha.context['segundas_vt'], [date(2026, 9, 28)])
        self.assertContains(folha, 'Pagamentos atrasados')

    def test_atrasados_ignora_intervalo_e_status_incompativel(self):
        response = self.client.get(reverse('lista_pagamentos_colaboradores'), {
            'visao': 'atrasados', 'status': 'pago', 'data_inicio': '2026-10-01',
        })
        self.assertEqual(response.context['total_pendente'], Decimal('1070'))
        self.assertEqual(response.context['segundas_vt'], [])
        self.assertNotIn('vt_semana', response.context)
        self.assertEqual({p.pk for p in response.context['pagamentos']}, {self.vt_antigo.pk, self.salario_antigo.pk})

    def test_pago_sai_dos_atrasados_e_permanece_no_historico(self):
        PagamentoColaborador.objects.filter(pk=self.salario_antigo.pk).update(status='pago', data_pagamento=date(2026, 9, 30))
        response = self.client.get(reverse('lista_pagamentos_colaboradores'), {'visao': 'atrasados'})
        self.assertEqual(response.context['total_pendente'], Decimal('70'))
        historico = self.client.get(reverse('relatorio_folha_pagamento'), {
            'visao': 'historico', 'data_inicio': '2026-09-01', 'data_fim': '2026-09-30',
        })
        self.assertIn(self.salario_antigo.pk, {p.pk for p in historico.context['pagamentos']})

    def test_programacao_e_beneficios_abrem_na_semana_atual(self):
        semana = self.client.get(reverse('programacao_vt'))
        self.assertEqual(semana.context['segunda'], date(2026, 9, 28))
        beneficios = self.client.get(reverse('visao_beneficios_colaboradores'))
        self.assertEqual([p.pk for p in beneficios.context['pagamentos']], [self.vt_atual.pk])

    def test_relatorio_atrasados_preserva_visao_e_filtro_individual(self):
        response = self.client.get(reverse('relatorio_folha_pagamento'), {
            'visao': 'atrasados', 'colaborador': self.pessoa.pk,
        })
        self.assertEqual(response.context['total_geral'], Decimal('1070'))
        self.assertIn('visao=atrasados', response.context['filtros_query'])
        self.assertIn(f'colaborador={self.pessoa.pk}', response.context['filtros_query'])
