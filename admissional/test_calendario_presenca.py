from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .calendario_presenca import montar_calendario_presenca
from .models import Colaborador, PresencaDiaria


class CalendarioPresencaTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('calendario', password='teste'))
        self.ana = Colaborador.objects.create(nome='Ana', unidade='Santos', status='ativo')
        self.bia = Colaborador.objects.create(nome='Bia', unidade='Santos', status='ativo')
        self.inativo = Colaborador.objects.create(nome='Inativo', unidade='Santos', status='inativo')
        self.hoje = patch('admissional.calendario_presenca.timezone.localdate', return_value=date(2026, 9, 26))
        self.hoje.start()
        self.addCleanup(self.hoje.stop)

    def calendario(self, **filtros):
        response = self.client.get(reverse('controle_presenca'), {'data': '2026-09-25', **filtros})
        self.assertEqual(response.status_code, 200)
        return response, response.context['calendario']

    def dias(self, calendario):
        return {dia['numero']: dia for semana in calendario['semanas'] for dia in semana if dia}

    def test_distingue_sem_registro_parcial_indefinido_completo_e_futuro(self):
        for pessoa, numero, status in [
            (self.ana, 2, 'presente'), (self.bia, 2, 'indefinido'),
            (self.ana, 3, 'falta'), (self.bia, 3, 'folga'),
            (self.ana, 4, 'atestado'), (self.bia, 4, 'presente'),
        ]:
            PresencaDiaria.objects.create(colaborador=pessoa, data=date(2026, 9, numero), status=status)
        response, calendario = self.calendario()
        dias = self.dias(calendario)
        self.assertEqual(calendario['total'], 2)
        self.assertEqual(calendario['pendentes'], 24)
        self.assertEqual(calendario['completos'], 2)
        self.assertIn('2 de 2 sem preenchimento', dias[1]['descricao'])
        self.assertIn('1 de 2 sem preenchimento', dias[2]['descricao'])
        self.assertEqual(dias[3]['estado'], 'completo')
        self.assertEqual(dias[4]['estado'], 'completo')
        self.assertEqual(dias[26]['estado'], 'pendente')
        self.assertEqual(dias[27]['estado'], 'futuro')
        self.assertTrue(dias[25]['selecionado'])
        self.assertContains(response, 'Salvar Presenças do Dia')
        self.assertContains(response, 'Exportar CSV filtrado')

    def test_respeita_filtros_de_pessoas_mas_nao_oculta_pendencias_por_situacao(self):
        PresencaDiaria.objects.create(colaborador=self.ana, data=date(2026, 9, 25), status='presente')
        response, calendario = self.calendario(unidade='Santos', q='Bia', situacao='presente')
        self.assertEqual(response.context['total_colaboradores_presenca'], 0)
        self.assertEqual(calendario['total'], 1)
        dia = self.dias(calendario)[25]
        self.assertEqual(dia['estado'], 'pendente')
        query = parse_qs(urlsplit(dia['url']).query)
        self.assertEqual(query['q'], ['Bia'])
        self.assertEqual(query['unidade'], ['Santos'])
        self.assertEqual(query['situacao'], ['presente'])
        self.assertEqual(query['data'], ['2026-09-25'])

    def test_sem_colaboradores_nao_marca_pendencias(self):
        _, calendario = self.calendario(unidade='Inexistente')
        self.assertEqual(calendario['pendentes'], 0)
        self.assertEqual(calendario['completos'], 0)
        self.assertTrue(all(d['estado'] == 'vazio' for d in self.dias(calendario).values()))

    def test_navega_meses_sem_mudar_lista_e_aceita_fevereiro_bissexto(self):
        response, calendario = self.calendario(mes_calendario='2024-02')
        self.assertEqual(response.context['data_selecionada'], date(2026, 9, 25))
        self.assertEqual(len(self.dias(calendario)), 29)
        self.assertIn('mes_calendario=2024-01', calendario['anterior'])
        self.assertIn('mes_calendario=2024-03', calendario['proximo'])
        _, calendario = self.calendario(mes_calendario='2025-12')
        self.assertIn('mes_calendario=2026-01', calendario['proximo'])

    def test_mes_invalido_retorna_mes_da_data_selecionada(self):
        for mes in ('invalido', '2026-13', '0000-01'):
            with self.subTest(mes=mes):
                _, calendario = self.calendario(mes_calendario=mes)
                self.assertEqual(calendario['titulo'], 'Setembro de 2026')

    def test_salvamento_atualiza_calendario(self):
        response = self.client.post(reverse('controle_presenca'), {
            'data': '2026-09-25', 'q': 'Ana',
            f'colaborador_{self.ana.pk}': '1', f'status_{self.ana.pk}': 'presente',
        }, follow=True)
        self.assertEqual(self.dias(response.context['calendario'])[25]['estado'], 'completo')

    def test_resumo_mensal_usa_duas_consultas(self):
        with self.assertNumQueries(2):
            calendario = montar_calendario_presenca(
                date(2026, 9, 25), '', {}, Colaborador.objects.filter(status='ativo'),
            )
        self.assertEqual(len(self.dias(calendario)), 30)
