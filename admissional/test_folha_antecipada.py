from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from .models import Colaborador, PagamentoColaborador, PresencaDiaria, ProgramacaoVT
from .calculo_folha import calcular_salario
from .programacao_vt import linhas_semana


class FolhaAntecipadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('folha', password='test-password')
        cls.pessoa = Colaborador.objects.create(nome='Pessoa folha', salario=3000, vale_transporte_semanal=100)

    def setUp(self):
        self.client.force_login(self.user)

    def salario(self, **kwargs):
        dados = {'mes': '2026-09', 'pessoa_id': self.pessoa.pk, 'salario_base': '3000,00',
            'dias_trabalhados': '30', 'faltas': '2', 'gratificacao': '200', 'outros_descontos': '150',
            'data_vencimento': '2026-10-05'}
        return self.client.post(reverse('programacao_salarios'), {**dados, **kwargs})

    def vt(self, **kwargs):
        dados = {'segunda': '2026-09-28', 'pessoa_id': self.pessoa.pk, 'antecipado': 'on',
            'decisao': 'pagar', 'valor': '100', 'dias_jornada': '5', 'dias_previstos': '5',
            'faltas_descontar': '0', 'desconto_adicional': '0'}
        return self.client.post(reverse('programacao_vt'), {**dados, **kwargs})

    def test_salario_gratificacao_integral_faltas_descontos_e_arredondamento(self):
        response = self.salario(valor='999999')
        self.assertEqual(response.status_code, 302)
        p = PagamentoColaborador.objects.get()
        self.assertEqual(p.valor, Decimal('2850'))
        self.assertEqual(p.gratificacao, Decimal('200'))
        self.assertEqual(p.faltas, Decimal('2'))
        self.assertEqual(calcular_salario(Decimal('2000'), Decimal('7'), 0, 100, 0), Decimal('566.67'))

    def test_revisao_nao_duplica_salario_e_nao_altera_presenca(self):
        PresencaDiaria.objects.create(colaborador=self.pessoa, data=date(2026,9,10), status='falta')
        self.salario()
        self.assertEqual(self.salario(faltas='1').status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.count(), 1)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('2950'))
        self.assertEqual(PresencaDiaria.objects.get().status, 'falta')
        page = self.client.get(reverse('programacao_salarios'), {'mes': '2026-09'})
        self.assertContains(page, '10/09/2026')
        self.assertContains(page, 'value="2026-10-05"')

    def test_formulario_individual_calcula_no_servidor(self):
        response = self.client.post(reverse('novo_pagamento_colaborador'), {
            'colaborador': self.pessoa.pk, 'tipo': 'salario', 'competencia': '2026-09-01',
            'competencia_fim': '2026-09-30', 'data_vencimento': '2026-10-05', 'status': 'pendente',
            'salario_base': '3000', 'dias_trabalhados': '30', 'faltas': '2',
            'gratificacao': '200', 'outros_descontos': '150', 'valor': '9999',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('2850'))

    def test_validacao_salario_e_preservacao_pago(self):
        for dados in ({'faltas':'31'}, {'dias_trabalhados':'31'}, {'outros_descontos':'9999'}, {'salario_base':''}):
            with self.subTest(dados=dados):
                self.assertEqual(self.salario(**dados).status_code, 400)
        self.assertFalse(PagamentoColaborador.objects.exists())
        self.salario()
        p = PagamentoColaborador.objects.get()
        p.status='pago'; p.save()
        self.assertEqual(self.salario().status_code, 400)
        p.refresh_from_db(); self.assertEqual(p.valor, Decimal('2850'))

    def test_vt_sem_presenca_e_novo_admitido_no_meio_da_semana(self):
        self.pessoa.data_admissao=date(2026,9,30); self.pessoa.save()
        self.assertEqual(self.vt(dias_previstos='3').status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('60'))
        self.assertTrue(ProgramacaoVT.objects.get().antecipado)

    def test_vt_desconta_uma_vez_com_diaria_anterior_e_revisao_manual(self):
        for _ in range(2):
            self.assertEqual(self.vt(faltas_descontar='2', diaria_desconto='15', desconto_adicional='5').status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.count(),1)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('65'))
        self.assertEqual(self.vt(faltas_descontar='0').status_code,302)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('100'))

    def test_vt_jornada_seis_e_pagamento_preservado(self):
        self.assertEqual(self.vt(valor='120',dias_jornada='6',dias_previstos='6',faltas_descontar='1').status_code,302)
        p=PagamentoColaborador.objects.get(); self.assertEqual(p.valor,Decimal('100'))
        p.status='pago'; p.save()
        self.assertEqual(self.vt(valor='900').status_code,400)
        p.refresh_from_db(); self.assertEqual(p.valor,Decimal('100'))

    def test_vt_valida_jornada_e_dias_sem_gerar_valores_incorretos(self):
        for dados in ({'dias_jornada':''},{'dias_jornada':'0'},{'dias_previstos':'6'}, {'faltas_descontar':'8'}, {'desconto_adicional':'200'}):
            with self.subTest(dados=dados): self.assertEqual(self.vt(**dados).status_code,400)
        self.assertFalse(PagamentoColaborador.objects.exists())

    def test_faltas_sugeridas_apenas_de_semana_antecipada_ja_paga(self):
        self.vt(segunda='2026-09-21')
        p=PagamentoColaborador.objects.get();p.status='pago';p.save()
        PresencaDiaria.objects.create(colaborador=self.pessoa,data=date(2026,9,23),status='falta')
        linha=linhas_semana(date(2026,9,28))[0]
        self.assertEqual(linha['faltas_descontar'],1)
        self.assertEqual(linha['datas_faltas'],[date(2026,9,23)])
        self.assertEqual(linha['valor_antecipado'],Decimal('80'))

    def test_perfil_de_consulta_nao_pode_salvar_folha(self):
        from core.models import PerfilUsuario
        user=User.objects.create_user('restrito')
        PerfilUsuario.objects.create(usuario=user,perfil='entregas_consulta')
        self.client.force_login(user)
        self.assertEqual(self.salario().status_code,403)
        self.assertEqual(self.vt().status_code,403)
