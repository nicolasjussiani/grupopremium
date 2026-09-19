from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Colaborador, PagamentoColaborador


class HistoricoValeTransporteTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username='diretoria_vt',
            email='diretoria@example.com',
            password='senha-forte-teste',
        )
        self.colaborador = Colaborador.objects.create(
            nome='Colaborador VT',
            tipo_contrato='clt',
            status='ativo',
        )
        self.outro_colaborador = Colaborador.objects.create(
            nome='Outro Colaborador',
            tipo_contrato='clt',
        )
        self.url = reverse(
            'historico_vt_colaborador', args=(self.colaborador.pk,)
        )

    def criar_pagamento(self, colaborador=None, **kwargs):
        dados = {
            'colaborador': colaborador or self.colaborador,
            'tipo': 'vale_transporte',
            'competencia': date(2026, 9, 14),
            'valor': Decimal('80.00'),
            'data_vencimento': date(2026, 9, 14),
            'status': 'pago',
            'data_pagamento': date(2026, 9, 14),
        }
        dados.update(kwargs)
        return PagamentoColaborador.objects.create(**dados)

    def test_exige_autenticacao(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/login/?next={self.url}')

    def test_mostra_somente_vts_pagos_do_colaborador(self):
        vt_pago = self.criar_pagamento()
        self.criar_pagamento(
            competencia=date(2026, 9, 21),
            data_vencimento=date(2026, 9, 21),
            data_pagamento=None,
            status='pendente',
        )
        self.criar_pagamento(
            tipo='salario',
            competencia=date(2026, 9, 1),
            data_vencimento=date(2026, 9, 5),
            data_pagamento=date(2026, 9, 5),
            recorrente=False,
        )
        self.criar_pagamento(colaborador=self.outro_colaborador)
        self.client.force_login(self.usuario)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['pagamentos']), [vt_pago])
        self.assertEqual(response.context['total_pago'], Decimal('80.00'))
        self.assertEqual(response.context['quantidade_pagamentos'], 1)
        self.assertContains(response, 'VTs pagos')
        self.assertContains(response, 'Cadastrar novo VT')

    def test_botao_vt_da_lista_abre_o_historico(self):
        self.client.force_login(self.usuario)
        response = self.client.get(reverse('lista_colaboradores'))
        self.assertContains(response, self.url)
        self.assertContains(response, 'Ver VTs pagos')
