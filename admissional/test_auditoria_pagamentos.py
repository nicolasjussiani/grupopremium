from datetime import date
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.models import PerfilUsuario

from .forms import PagamentoColaboradorForm
from .models import Colaborador, PagamentoColaborador, PresencaDiaria


class AuditoriaPagamentosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('auditoria_folha')
        cls.pessoa = Colaborador.objects.create(nome='Pessoa auditoria')

    def setUp(self):
        self.client.force_login(self.user)
        self.dados = {
            'colaborador': self.pessoa.pk, 'tipo': 'salario',
            'competencia': '2026-09-01', 'competencia_fim': '2026-09-30',
            'data_vencimento': '2026-09-05', 'valor': '2000,00',
            'status': 'pendente', 'data_pagamento': '',
        }
        self.filtros = {'data_inicio': '2026-09-01', 'data_fim': '2026-09-30'}

    def pagamento(self, **extras):
        dados = dict(colaborador=self.pessoa, tipo='salario',
                     competencia=date(2026, 9, 1), competencia_fim=date(2026, 9, 30),
                     data_vencimento=date(2026, 9, 5), valor=Decimal('2000'))
        dados.update(extras)
        return PagamentoColaborador.objects.create(**dados)

    def test_vt_pendente_descarta_data_pagamento_enviada(self):
        form = PagamentoColaboradorForm(data={
            **self.dados, 'tipo': 'vale_transporte',
            'competencia': '2026-09-08', 'data_pagamento': '2026-10-06',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().data_pagamento)

    def test_edicao_nao_permite_desfazer_baixa_ou_alterar_valor_pago(self):
        pagamento = self.pagamento(status='pago', data_pagamento=date(2026, 9, 5))
        for alteracao in ({'status': 'pendente'}, {'status': 'cancelado'}, {'valor': '1,00'}):
            with self.subTest(alteracao=alteracao):
                response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
                    **self.dados, 'status': 'pago', 'data_pagamento': '2026-09-05', **alteracao,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].non_field_errors())
                pagamento.refresh_from_db()
                self.assertEqual(pagamento.status, 'pago')
                self.assertEqual(pagamento.valor, Decimal('2000'))

    def test_edicao_pago_permite_observacao_sem_mudar_baixa(self):
        pagamento = self.pagamento(status='pago', data_pagamento=date(2026, 9, 5))
        response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
            **self.dados, 'status': 'pago', 'data_pagamento': '2026-09-05', 'observacao': 'Conferido',
        })
        self.assertEqual(response.status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.observacao, 'Conferido')

    def test_edicao_pago_legado_sem_fim_competencia_permite_observacao(self):
        pagamento = self.pagamento(status='pago', data_pagamento=date(2026, 9, 5), competencia_fim=None)
        response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
            **self.dados, 'status': 'pago', 'data_pagamento': '2026-09-05',
            'competencia_fim': '', 'observacao': 'Conferido',
        })
        self.assertEqual(response.status_code, 302)

    def test_edicao_observacao_de_vt_pago_nao_gera_nova_obrigacao(self):
        pagamento = self.pagamento(tipo='vale_transporte', status='pago', data_pagamento=date(2026, 9, 7))
        response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
            **self.dados, 'tipo': 'vale_transporte', 'status': 'pago',
            'competencia': pagamento.competencia.isoformat(),
            'competencia_fim': pagamento.competencia_fim.isoformat(),
            'data_vencimento': pagamento.data_vencimento.isoformat(),
            'data_pagamento': '2026-09-07', 'observacao': 'Conferido',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.count(), 1)

    def test_financeiro_acessa_historico_sem_acesso_a_edicao_de_colaborador(self):
        usuario = User.objects.create_user('auditoria_financeiro')
        PerfilUsuario.objects.create(usuario=usuario, perfil='financeiro')
        self.client.force_login(usuario)
        response = self.client.get(reverse('historico_vt_colaborador', args=[self.pessoa.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('editar_colaborador', args=[self.pessoa.pk]))
        self.assertNotEqual(response.status_code, 200)

    def test_identificador_invalido_no_atalho_nao_causa_erro_500(self):
        for identificador in ('²', '9' * 40):
            with self.subTest(identificador=identificador):
                response = self.client.get(reverse('novo_pagamento_colaborador'), {
                    'colaborador': identificador, 'tipo': 'salario',
                })
                self.assertEqual(response.status_code, 200)

    def test_painel_financeiro_usa_mes_local_e_vencimento_de_pendente(self):
        self.pagamento(data_pagamento=date(2026, 10, 5))
        with patch('financeiro.views.timezone.localdate', return_value=date(2026, 9, 30)):
            response = self.client.get(reverse('painel_financeiro'))
        self.assertEqual(response.context['folha_mes_pendente'], Decimal('2000'))

    def test_filtro_individual_preservado_no_retorno(self):
        response = self.client.get(reverse('relatorio_folha_pagamento'), {
            **self.filtros, 'colaborador': self.pessoa.pk,
        })
        self.assertEqual(parse_qs(response.context['filtros_query']).get('colaborador'), [str(self.pessoa.pk)])

    def test_presencas_indefinidas_nao_equivalem_a_zero_dias(self):
        self.pagamento()
        presenca = PresencaDiaria.objects.create(
            colaborador=self.pessoa, data=date(2026, 9, 10), status='indefinido',
        )
        response = self.client.get(reverse('lista_pagamentos_colaboradores'), self.filtros)
        self.assertIsNone(response.context['pagamentos'][0].dias_trabalhados_exibicao)
        presenca.status = 'falta'
        presenca.save()
        response = self.client.get(reverse('lista_pagamentos_colaboradores'), self.filtros)
        self.assertEqual(response.context['pagamentos'][0].dias_trabalhados_exibicao, 0)

    def test_pendente_legado_filtra_por_vencimento_sem_quebrar_resumo(self):
        pagamento = self.pagamento(data_vencimento=date(2026, 8, 5))
        PagamentoColaborador.objects.filter(pk=pagamento.pk).update(data_pagamento=date(2026, 9, 5))
        response = self.client.get(reverse('lista_pagamentos_colaboradores'), self.filtros)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_pendente'], 0)

    def test_conflito_concorrente_no_cadastro_vira_erro_de_formulario(self):
        with patch('admissional.views.PagamentoColaborador.save', side_effect=IntegrityError('conflito')):
            response = self.client.post(reverse('novo_pagamento_colaborador'), self.dados)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertFalse(PagamentoColaborador.objects.exists())

    def test_conflito_concorrente_na_edicao_preserva_registro(self):
        pagamento = self.pagamento()
        with patch('admissional.views.PagamentoColaborador.save', side_effect=IntegrityError('conflito')):
            response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
                **self.dados, 'valor': '2100,00',
            })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.valor, Decimal('2000'))
