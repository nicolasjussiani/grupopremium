from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import Colaborador, PagamentoColaborador, PresencaDiaria, ProgramacaoVT
from .programacao_vt import linhas_semana, segundas_no_periodo, resumo_semana


class ProgramacaoVTTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser('vt_admin', password='test-only-password')
        cls.pessoa = Colaborador.objects.create(nome='Ana VT', vale_transporte_semanal=80)

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse('programacao_vt')

    def decidir(self, decisao='pagar', **extras):
        if not PresencaDiaria.objects.filter(colaborador=self.pessoa).exists():
            PresencaDiaria.objects.bulk_create([
                PresencaDiaria(colaborador=self.pessoa, data=date(2026, 9, dia), status='presente')
                for dia in range(21, 28)
            ])
        return self.client.post(self.url, {
            'segunda': '2026-09-28', 'pessoa_id': self.pessoa.pk,
            'decisao': decisao, 'valor': '80.00', **extras,
        })

    def pagamento(self, segunda=date(2026, 9, 21), **extras):
        return PagamentoColaborador.objects.create(
            colaborador=self.pessoa, tipo='vale_transporte', competencia=segunda,
            data_vencimento=segunda, valor=80, **extras,
        )

    def test_calendario_inclui_todas_segundas_inclusive_quinta_e_virada_ano(self):
        self.assertEqual(list(segundas_no_periodo(date(2026, 3, 1), date(2026, 3, 31))),
                         [date(2026, 3, d) for d in (2, 9, 16, 23, 30)])
        self.assertEqual(list(segundas_no_periodo(date(2026, 12, 28), date(2027, 1, 5))),
                         [date(2026, 12, 28), date(2027, 1, 4)])

    def test_dia_28_aparece_sem_baixa_anterior_e_get_nao_cria_pagamentos(self):
        anterior = self.pagamento()
        with patch('admissional.views_vt.timezone.localdate', return_value=date(2026, 9, 26)):
            resposta = self.client.get(self.url)
        self.assertContains(resposta, '28/09/2026')
        self.assertContains(resposta, 'Ana VT')
        self.assertEqual(resposta.context['linhas'][0]['situacao'], 'revisar')
        self.assertEqual(PagamentoColaborador.objects.count(), 1)
        self.assertFalse(ProgramacaoVT.objects.exists())
        self.assertEqual(self.decidir().status_code, 302)
        anterior.refresh_from_db()
        self.assertEqual(anterior.status, 'pendente')
        self.assertEqual(PagamentoColaborador.objects.get(data_vencimento='2026-09-28').status, 'pendente')

    def test_folha_tem_acesso_direto_ao_dia_28(self):
        resposta = self.client.get(reverse('lista_pagamentos_colaboradores'),
                                   {'data_inicio': '2026-09-01', 'data_fim': '2026-09-30'})
        self.assertContains(resposta, f'{self.url}?segunda=2026-09-28')

    def test_folha_dia_28_lista_pessoas_sem_pagamento_e_salva_no_mesmo_filtro(self):
        filtros = {'data_inicio': '2026-09-28', 'data_fim': '2026-09-28'}
        folha_url = reverse('lista_pagamentos_colaboradores')
        resposta = self.client.get(folha_url, filtros)
        self.assertContains(resposta, 'Pessoas para o pagamento de segunda-feira · 28/09/2026')
        self.assertContains(resposta, 'Ana VT')
        self.assertContains(resposta, 'Pagar VT')
        self.assertContains(resposta, f'action="{self.url}"')
        self.assertEqual(resposta.context['vt_semana']['segunda'], date(2026, 9, 28))
        self.assertFalse(PagamentoColaborador.objects.exists())
        resposta = self.decidir(
            voltar_folha='1', filtros_folha='data_inicio=2026-09-28&data_fim=2026-09-28',
        )
        self.assertRedirects(resposta, folha_url + '?data_inicio=2026-09-28&data_fim=2026-09-28&segunda_vt=2026-09-28')
        resposta = self.client.get(resposta['Location'])
        self.assertEqual(resposta.context['total_pendente'], Decimal('80'))
        self.assertEqual(resposta.context['vt_semana']['linhas'][0]['situacao'], 'pagar')

    def test_lista_vt_embutida_respeita_filtros_de_pessoa_e_periodo(self):
        outra = Colaborador.objects.create(nome='Bia VT', unidade='Santos')
        filtros = {'data_inicio': '2026-09-28', 'data_fim': '2026-09-28'}
        url = reverse('lista_pagamentos_colaboradores')
        resposta = self.client.get(url, {**filtros, 'q': 'Bia'})
        self.assertEqual([l['pessoa'].pk for l in resposta.context['vt_semana']['linhas']], [outra.pk])
        resposta = self.client.get(url, {**filtros, 'colaborador': self.pessoa.pk})
        self.assertEqual(len(resposta.context['vt_semana']['linhas']), 1)
        resposta = self.client.get(url, {**filtros, 'tipo': 'salario'})
        self.assertNotIn('vt_semana', resposta.context)
        resposta = self.client.get(url, {'data_inicio': '2026-09-29', 'data_fim': '2026-09-29'})
        self.assertNotIn('vt_semana', resposta.context)

    def test_presencas_somente_da_semana_anterior_e_ausencia_de_dados(self):
        for dia, status in [(20, 'presente'), (21, 'presente'), (22, 'falta'), (23, 'indefinido'),
                            (27, 'presente'), (28, 'presente')]:
            PresencaDiaria.objects.create(colaborador=self.pessoa, data=date(2026, 9, dia), status=status)
        linha = linhas_semana(date(2026, 9, 28))[0]
        self.assertEqual(linha['dias'], 2)
        self.assertEqual(linha['datas'], [date(2026, 9, 21), date(2026, 9, 27)])
        self.assertEqual(linha['definidos'], 3)
        self.assertIsNone(linhas_semana(date(2026, 10, 12))[0]['dias'])
        self.pagamento(date(2026, 9, 28))
        for nome in ['lista_pagamentos_colaboradores', 'visao_beneficios_colaboradores', 'relatorio_folha_pagamento']:
            resposta = self.client.get(reverse(nome), {'data_inicio': '2026-09-28', 'data_fim': '2026-09-28'})
            self.assertEqual(resposta.context['pagamentos'][0].dias_trabalhados_exibicao, 2)

    def test_zero_presencas_definidas_diferente_de_sem_informacao(self):
        PresencaDiaria.objects.create(colaborador=self.pessoa, data=date(2026, 9, 21), status='indefinido')
        self.assertIsNone(linhas_semana(date(2026, 9, 28))[0]['dias'])
        PresencaDiaria.objects.create(colaborador=self.pessoa, data=date(2026, 9, 22), status='falta')
        self.assertEqual(linhas_semana(date(2026, 9, 28))[0]['dias'], 0)

    def test_calendario_distingue_falta_atestado_e_sem_registro(self):
        PresencaDiaria.objects.create(colaborador=self.pessoa, data=date(2026, 9, 21), status='falta')
        PresencaDiaria.objects.create(colaborador=self.pessoa, data=date(2026, 9, 22), status='atestado')
        semana = linhas_semana(date(2026, 9, 28))[0]['dias_semana']
        self.assertEqual(len(semana), 7)
        self.assertEqual([dia['status'] for dia in semana[:3]], ['falta', 'atestado', 'indefinido'])
        self.assertEqual(semana[-1]['data'], date(2026, 9, 27))

    def test_resumo_conta_decisoes_salvas_e_erro_preserva_edicao(self):
        self.decidir()
        linhas = linhas_semana(date(2026, 9, 28))
        self.assertEqual(resumo_semana(linhas)['valor_pendente'], Decimal('80'))
        resposta = self.decidir(valor='0')
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.context['linhas'][0]['valor'], '0')
        self.assertEqual(resposta.context['linhas'][0]['decisao'], 'pagar')
        self.assertEqual(resposta.context['resumo_vt']['valor_pendente'], Decimal('80'))
        self.decidir('nao')
        resumo = resumo_semana(linhas_semana(date(2026, 9, 28)))
        self.assertEqual(resumo['nao'], 1)
        self.assertEqual(resumo['pagar'], 0)
        self.assertEqual(resumo['valor_pendente'], 0)

    def test_repetir_e_alterar_valor_nao_duplica(self):
        self.decidir()
        self.decidir()
        self.assertEqual(self.decidir(valor='90,50').status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.count(), 1)
        self.assertEqual(PagamentoColaborador.objects.get().valor, Decimal('90.50'))
        self.assertEqual(ProgramacaoVT.objects.count(), 1)

    def test_nao_recebe_fica_salvo_e_nao_bloqueia_proxima_semana(self):
        self.assertEqual(self.decidir('nao', valor='').status_code, 302)
        self.assertEqual(linhas_semana(date(2026, 9, 28))[0]['situacao'], 'nao')
        self.assertFalse(PagamentoColaborador.objects.exists())
        anterior = self.pagamento(status='pago')
        self.assertEqual(anterior.criar_proxima_recorrencia(), (None, False))
        self.assertEqual(linhas_semana(date(2026, 10, 5))[0]['situacao'], 'revisar')
        self.assertEqual(self.decidir().status_code, 302)

    def test_retirar_cancela_pendente_sem_apagar_e_pode_reincluir(self):
        self.decidir()
        original = PagamentoColaborador.objects.get()
        self.decidir('nao')
        original.refresh_from_db()
        self.assertEqual(original.status, 'cancelado')
        self.assertFalse(original.recorrente)
        self.decidir()
        self.assertEqual(PagamentoColaborador.objects.filter(status='pendente').count(), 1)
        self.assertEqual(PagamentoColaborador.objects.count(), 2)

    def test_pagamento_existente_reutilizado_e_pago_protegido(self):
        pagamento = self.pagamento(date(2026, 9, 28))
        self.decidir()
        self.assertEqual(PagamentoColaborador.objects.count(), 1)
        pagamento.status = 'pago'
        pagamento.save()
        self.assertEqual(self.decidir('nao').status_code, 400)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')

    def test_valor_data_e_pessoa_invalidos_nao_criam_lancamentos(self):
        for dados in [{'valor': ''}, {'valor': '0'}, {'valor': '-1'}, {'valor': 'NaN'},
                      {'segunda': '2026-09-29'}, {'segunda': 'invalida'}, {'pessoa_id': 999999}]:
            self.assertEqual(self.decidir(**dados).status_code, 400, dados)
        for campos in [{'status': 'inativo'}, {'status': 'desligado'}, {'tipo_contrato': 'invalido'},
                       {'data_admissao': date(2026, 10, 1)}]:
            pessoa = Colaborador.objects.create(nome='Indisponível', **campos)
            self.assertEqual(self.decidir(pessoa_id=pessoa.pk).status_code, 400)
        self.assertFalse(PagamentoColaborador.objects.exists())
        self.assertFalse(ProgramacaoVT.objects.exists())

    def test_permissoes_e_csrf(self):
        leitor = User.objects.create_user('leitor_vt')
        leitor.user_permissions.add(Permission.objects.get(codename='view_pagamentocolaborador'))
        self.client.force_login(leitor)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.decidir().status_code, 403)
        self.client.force_login(self.usuario)
        from django.test import Client
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.usuario)
        self.assertEqual(protegido.post(self.url, {}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_pj_com_presenca_aparece_e_gera_ajuda_sem_transformar_em_vt(self):
        pj = Colaborador.objects.create(nome='Adriana exemplo', tipo_contrato='pj', ajuda_custo_semanal=120)
        PresencaDiaria.objects.create(colaborador=pj, data=date(2026, 9, 21), status='presente')
        resposta = self.client.get(self.url, {'segunda': '2026-09-28'})
        self.assertContains(resposta, 'Adriana exemplo')
        self.assertContains(resposta, 'Pagar ajuda')
        linha = next(l for l in resposta.context['linhas'] if l['pessoa'].pk == pj.pk)
        self.assertEqual(linha['tipo_beneficio'], 'ajuda_custo')
        self.assertEqual(linha['valor'], Decimal('120'))
        self.assertEqual(linha['dias'], 1)
        self.assertEqual(resposta.context['resumo_vt']['pj'], 1)
        self.assertEqual(resposta.context['resumo_vt']['clt'], 1)
        for _ in range(2):
            self.assertEqual(self.decidir(pessoa_id=pj.pk, valor='120', tipo='vale_transporte').status_code, 302)
        pagamento = PagamentoColaborador.objects.get(colaborador=pj)
        self.assertEqual(pagamento.tipo, 'ajuda_custo')
        self.assertEqual(pagamento.status, 'pendente')
        self.assertEqual(pagamento.valor, Decimal('17.14'))

    def test_pj_nao_recebe_impede_recorrencia_e_respeita_filtro_da_folha(self):
        pj = Colaborador.objects.create(nome='Adriana exemplo', tipo_contrato='pj')
        PresencaDiaria.objects.create(colaborador=pj, data=date(2026, 9, 21), status='presente')
        filtros = {'data_inicio': '2026-09-28', 'data_fim': '2026-09-28'}
        url = reverse('lista_pagamentos_colaboradores')
        for tipo, esperado in [('vale_transporte', self.pessoa.pk), ('ajuda_custo', pj.pk)]:
            resposta = self.client.get(url, {**filtros, 'tipo': tipo})
            self.assertEqual([l['pessoa'].pk for l in resposta.context['vt_semana']['linhas']], [esperado])
        self.decidir(pessoa_id=pj.pk)
        resposta = self.client.get(url, filtros)
        self.assertEqual(resposta.context['pagamentos'][0].dias_trabalhados_exibicao, 1)
        self.assertEqual(self.decidir('nao', pessoa_id=pj.pk).status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.get(colaborador=pj).status, 'cancelado')
        anterior = PagamentoColaborador.objects.create(
            colaborador=pj, tipo='ajuda_custo', competencia=date(2026, 9, 21),
            data_vencimento=date(2026, 9, 21), valor=80, status='pago',
        )
        self.assertEqual(anterior.criar_proxima_recorrencia(), (None, False))
        self.assertEqual(PagamentoColaborador.objects.filter(colaborador=pj, data_vencimento='2026-09-28').count(), 1)
