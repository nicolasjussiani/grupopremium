from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador, PresencaDiaria
from core.models import PerfilUsuario


class RelatorioFolhaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rh = User.objects.create_user('rh_relatorio')
        PerfilUsuario.objects.create(usuario=cls.rh, perfil='rh')
        cls.ana = Colaborador.objects.create(nome='Ana Relatório', unidade='Santos', tipo_contrato='clt')
        cls.beto = Colaborador.objects.create(nome='Beto Freelancer', unidade='Campinas', categoria_trabalho='freelancer')
        cls.inativo = Colaborador.objects.create(nome='Pessoa desligada', status='desligado')
        cls.salario = cls.pagamento(cls.ana, 'salario', '2000.00', date(2026, 9, 5),
                                    status='pago', data_pagamento=date(2026, 9, 5), chave_pix='ana@example.com')
        cls.vt = cls.pagamento(cls.ana, 'vale_transporte', '100.00', date(2026, 9, 7))
        cls.vt2 = cls.pagamento(cls.ana, 'vale_transporte', '100.00', date(2026, 9, 14))
        cls.freela = cls.pagamento(cls.beto, 'freelancer', '300.00', date(2026, 9, 10),
                                   dias_trabalhados=3, valor_diaria=100, chave_pix='pix-freela')
        cls.cancelado = cls.pagamento(cls.ana, 'reembolso', '999.00', date(2026, 9, 12), status='cancelado')
        cls.pagamento(cls.inativo, 'salario', '5000.00', date(2026, 9, 5), status='pago', data_pagamento=date(2026, 9, 5))
        cls.pagamento(cls.ana, 'salario', '2100.00', date(2026, 10, 5))
        PresencaDiaria.objects.create(colaborador=cls.ana, data=date(2026, 9, 1), status='presente')

    @classmethod
    def pagamento(cls, colaborador, tipo, valor, vencimento, **extras):
        return PagamentoColaborador.objects.create(
            colaborador=colaborador, tipo=tipo, valor=Decimal(valor),
            competencia=vencimento, data_vencimento=vencimento, **extras,
        )

    def setUp(self):
        self.client.force_login(self.rh)
        self.url = reverse('relatorio_folha_pagamento')
        self.filtros = {'data_inicio': '2026-09-01', 'data_fim': '2026-09-30'}

    def test_geral_confere_com_folha_e_separa_salario_vt_diarias(self):
        response = self.client.get(self.url, self.filtros)
        folha = self.client.get(reverse('lista_pagamentos_colaboradores'), self.filtros)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_geral'], Decimal('2500'))
        self.assertEqual(response.context['total_pessoas'], 2)
        self.assertEqual(response.context['total_pago'], folha.context['total_pago'])
        self.assertEqual(response.context['total_pendente'], folha.context['total_pendente'])
        self.assertEqual(len(response.context['pagamentos']), 4)
        tipos = {t['nome']: t['total'] for t in response.context['totais_tipo']}
        self.assertEqual(tipos, {'Salário': Decimal('2000'), 'Vale-transporte': Decimal('200'), 'Freelancer': Decimal('300')})
        self.assertNotContains(response, 'Pessoa desligada')
        self.assertContains(response, 'ana@example.com')
        self.assertContains(response, 'Imprimir / Salvar PDF')
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_individual_freelancer_com_pix_e_dias(self):
        response = self.client.get(self.url, {**self.filtros, 'colaborador': self.beto.pk})
        self.assertEqual(response.context['total_geral'], Decimal('300'))
        self.assertEqual(response.context['total_pessoas'], 1)
        self.assertEqual(response.context['colaborador_selecionado'], self.beto)
        self.assertEqual([p.pk for p in response.context['pagamentos']], [self.freela.pk])
        self.assertEqual(response.context['pagamentos'][0].dias_trabalhados_exibicao, 3)
        self.assertContains(response, 'pix-freela')
        self.assertNotContains(response, 'ana@example.com')

    def test_filtros_combinados_e_cancelados_fora_do_total(self):
        response = self.client.get(self.url, {**self.filtros, 'unidade': 'Santos', 'tipo': 'vale_transporte', 'status': 'pendente', 'categoria': 'fixo'})
        self.assertEqual(response.context['total_geral'], Decimal('200'))
        self.assertEqual(len(response.context['pagamentos']), 2)
        cancelados = self.client.get(self.url, {**self.filtros, 'status': 'cancelado'})
        self.assertEqual(cancelados.context['total_geral'], 0)
        self.assertEqual(cancelados.context['total_cancelado'], Decimal('999'))
        self.assertEqual(len(cancelados.context['pagamentos']), 1)

    def test_periodo_usa_pagamento_real_e_vencimento_para_pendente(self):
        PagamentoColaborador.objects.filter(pk=self.salario.pk).update(data_pagamento=date(2026, 10, 1))
        response = self.client.get(self.url, self.filtros)
        self.assertEqual(response.context['total_geral'], Decimal('500'))
        outubro = self.client.get(self.url, {'data_inicio': '2026-10-01', 'data_fim': '2026-10-31', 'status': 'pago'})
        self.assertEqual(outubro.context['total_geral'], Decimal('2000'))

    def test_vazio_datas_invertidas_e_identificador_invalido(self):
        vazio = self.client.get(self.url, {**self.filtros, 'q': 'ninguém encontrado'})
        self.assertContains(vazio, 'Nenhum pagamento encontrado')
        self.assertEqual(vazio.context['total_geral'], 0)
        invertido = self.client.get(self.url, {'data_inicio': '2026-09-30', 'data_fim': '2026-09-01'})
        self.assertEqual(invertido.context['total_geral'], Decimal('2500'))
        self.assertEqual(self.client.get(self.url, {'data_inicio': '2026-02-31'}).status_code, 200)
        self.assertEqual(self.client.get(self.url, {'colaborador': '999999999999999999999999999999999'}).status_code, 404)

    def test_acesso_restrito_e_liberado_para_financeiro(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        usuario = User.objects.create_user('sem_permissao_relatorio')
        perfil = PerfilUsuario.objects.create(usuario=usuario, perfil='rh')
        self.client.force_login(usuario)
        # With a module profile that allows attendance but not payroll.
        perfil.perfil = 'sesmet'
        perfil.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        perfil.perfil = 'financeiro'
        perfil.save()
        self.assertEqual(self.client.get(self.url, self.filtros).status_code, 200)
