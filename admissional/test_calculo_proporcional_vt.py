from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Colaborador, PagamentoColaborador, PresencaDiaria, ProgramacaoVT
from .programacao_vt import linhas_semana, valor_proporcional


class CalculoProporcionalVTTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser('calculo_admin', password='test-only-password')
        cls.pessoa = Colaborador.objects.create(nome='Pessoa exemplo', vale_transporte_semanal=140)

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse('programacao_vt')

    def presencas(self, *status):
        PresencaDiaria.objects.bulk_create([
            PresencaDiaria(colaborador=self.pessoa, data=date(2026, 9, 21) + timedelta(days=i), status=s)
            for i, s in enumerate(status)
        ])

    def salvar(self, **extras):
        return self.client.post(self.url, {
            'segunda': '2026-09-28', 'pessoa_id': self.pessoa.pk,
            'decisao': 'pagar', 'valor': '140', **extras,
        })

    def test_desconta_falta_folga_atestado_e_ignora_dias_fora_da_semana(self):
        self.presencas('presente', 'presente', 'presente', 'falta', 'atestado', 'folga', 'indefinido')
        PresencaDiaria.objects.create(colaborador=self.pessoa, data=date(2026, 9, 28), status='presente')
        self.assertEqual(self.salvar(dias_presentes='7', valor_calculado='140').status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('60'))
        registro = ProgramacaoVT.objects.get()
        self.assertEqual(registro.valor_semana_completa, Decimal('140'))
        self.assertEqual(registro.dias_presentes, 3)
        linha = linhas_semana(date(2026, 9, 28))[0]
        self.assertEqual(linha['valor'], Decimal('140'))
        self.assertEqual(linha['valor_calculado'], Decimal('60'))
        self.assertEqual(linha['dias_pendentes'], 1)

    def test_sete_presencas_pagam_semana_completa_e_arredonda_so_total(self):
        self.assertEqual(valor_proporcional(Decimal('100'), 6), Decimal('85.71'))
        self.assertEqual(valor_proporcional(Decimal('87.50'), 6), Decimal('75.00'))
        self.presencas(*(['presente'] * 7))
        self.assertEqual(self.salvar(valor='87,50').status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('87.50'))

    def test_salvar_novamente_nao_desconta_duas_vezes_e_recalcula_presenca(self):
        self.presencas(*(['presente'] * 5), 'falta', 'folga')
        for _ in range(2):
            self.assertEqual(self.salvar().status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.count(), 1)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('100'))
        PresencaDiaria.objects.filter(status='falta').update(status='presente')
        self.assertEqual(self.salvar().status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('120'))

    def test_sem_presencas_nao_cria_pagamento_zero_mas_permite_nao_precisa(self):
        resposta = self.salvar()
        self.assertContains(resposta, 'O valor calculado é R$ 0,00', status_code=400)
        self.assertFalse(PagamentoColaborador.objects.exists())
        self.assertFalse(ProgramacaoVT.objects.exists())
        self.assertEqual(self.salvar(decisao='nao', valor='').status_code, 302)
        self.assertFalse(ProgramacaoVT.objects.get().pagar)

    def test_pagamento_antigo_nao_vira_base_e_get_nao_altera_valor(self):
        self.presencas(*(['presente'] * 5))
        antigo = PagamentoColaborador.objects.create(
            colaborador=self.pessoa, tipo='vale_transporte', competencia=date(2026, 9, 28),
            data_vencimento=date(2026, 9, 28), valor=87.50,
        )
        resposta = self.client.get(self.url, {'segunda': '2026-09-28'})
        self.assertContains(resposta, 'Valor da semana completa (7 dias)')
        self.assertContains(resposta, 'Pagamento salvo: R$ 87,50')
        self.assertEqual(resposta.context['linhas'][0]['valor'], Decimal('140'))
        antigo.refresh_from_db()
        self.assertEqual(antigo.valor, Decimal('87.50'))

    def test_proxima_semana_reutiliza_base_completa_e_nao_recorrencia_liquida(self):
        self.presencas(*(['presente'] * 5))
        self.salvar()
        pagamento = PagamentoColaborador.objects.get()
        pagamento.status = 'pago'
        pagamento.save()
        self.assertEqual(pagamento.criar_proxima_recorrencia(), (None, False))
        linha = linhas_semana(date(2026, 10, 5))[0]
        self.assertEqual(linha['valor'], Decimal('140'))
        self.assertEqual(linha['situacao'], 'revisar')
        self.assertEqual(self.salvar(valor='700').status_code, 400)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.valor, Decimal('100'))
        self.assertEqual(ProgramacaoVT.objects.get().valor_semana_completa, Decimal('140'))

    def test_pj_recebe_ajuda_proporcional(self):
        self.pessoa.tipo_contrato = 'pj'
        self.pessoa.save()
        self.presencas(*(['presente'] * 6), 'folga')
        self.assertEqual(self.salvar(valor='87.50').status_code, 302)
        pagamento = PagamentoColaborador.objects.get()
        self.assertEqual(pagamento.tipo, 'ajuda_custo')
        self.assertEqual(pagamento.valor, Decimal('75'))
