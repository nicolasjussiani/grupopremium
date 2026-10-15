from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from admissional.models import Colaborador
from core.models import Notificacao
from sesmet.models import EquipamentoProtecao, RegistroEPI
from sesmet.services import sincronizar_alertas_epi


class CicloEPI90DiasTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser(
            'seguranca_teste', 'seguranca@example.com', 'senha-forte'
        )
        grupo = Group.objects.create(name='SESMET_Tecnico')
        self.usuario.groups.add(grupo)
        self.colaborador = Colaborador.objects.create(nome='Pessoa Operadora')
        self.equipamento = EquipamentoProtecao.objects.create(
            nome='Capacete', dias_durabilidade=30, estoque_atual=5
        )
        self.client = Client()
        self.client.force_login(self.usuario)

    def test_entrega_sempre_abre_ciclo_de_90_dias(self):
        hoje = timezone.localdate()
        registro = RegistroEPI.objects.create(
            colaborador=self.colaborador,
            equipamento=self.equipamento,
            data_movimentacao=hoje,
        )

        self.assertEqual(registro.data_validade, hoje + timedelta(days=90))
        self.assertTrue(registro.ciclo_ativo)

    def test_nova_entrega_encerra_ciclo_anterior_do_mesmo_produto(self):
        anterior = RegistroEPI.objects.create(
            colaborador=self.colaborador,
            equipamento=self.equipamento,
            data_movimentacao=timezone.localdate() - timedelta(days=30),
        )
        novo = RegistroEPI.objects.create(
            colaborador=self.colaborador,
            equipamento=self.equipamento,
            data_movimentacao=timezone.localdate(),
        )

        anterior.refresh_from_db()
        self.assertFalse(anterior.ciclo_ativo)
        self.assertTrue(novo.ciclo_ativo)

    def test_formulario_precisa_apenas_colaborador_e_produto(self):
        response = self.client.post(reverse('registrar_epi'), {
            'colaborador': self.colaborador.pk,
            'equipamento': self.equipamento.pk,
        })

        self.assertRedirects(response, reverse('dashboard_sesmet'))
        registro = RegistroEPI.objects.get()
        self.assertEqual(registro.quantidade, 1)
        self.assertEqual(registro.tipo_movimentacao, 'retirada')
        self.assertEqual(
            registro.data_validade, timezone.localdate() + timedelta(days=90)
        )

    def test_alerta_urgente_e_enviado_uma_unica_vez(self):
        registro = RegistroEPI.objects.create(
            colaborador=self.colaborador,
            equipamento=self.equipamento,
            data_movimentacao=timezone.localdate(),
        )
        registro.data_validade = timezone.localdate() + timedelta(days=7)
        registro.save(update_fields=['data_validade'])

        sincronizar_alertas_epi()
        sincronizar_alertas_epi()

        registro.refresh_from_db()
        self.assertEqual(registro.nivel_alerta, 'urgente')
        alertas = Notificacao.objects.filter(
            destinatario=self.usuario,
            titulo='EPIs vencem em até 7 dias',
        )
        self.assertEqual(alertas.count(), 1)

    def test_matriz_mostra_produto_e_responsavel(self):
        RegistroEPI.objects.create(
            colaborador=self.colaborador,
            equipamento=self.equipamento,
            data_movimentacao=timezone.localdate(),
            registrado_por=self.usuario,
        )

        response = self.client.get(reverse('matriz_epis'))

        self.assertContains(response, 'Capacete')
        self.assertContains(response, 'seguranca_teste')


class EdicaoEstoqueEPITest(TestCase):
    def setUp(self):
        usuario = User.objects.create_superuser('estoque_teste', 'estoque@example.com', 'senha-forte')
        self.client.force_login(usuario)
        self.colaborador = Colaborador.objects.create(nome='Pessoa Operadora')
        self.equipamento = EquipamentoProtecao.objects.create(nome='Capacete', estoque_atual=5)
        self.url = reverse('editar_equipamento', args=[self.equipamento.pk])

    def formulario(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="versao_equipamento"')
        return {
            'nome': 'Capacete revisado', 'estoque_atual': '5',
            'versao_equipamento': response.context['versao_equipamento'],
        }

    def retirar(self, quantidade=1):
        RegistroEPI.objects.create(
            colaborador=self.colaborador, equipamento=self.equipamento,
            data_movimentacao=timezone.localdate(), quantidade=quantidade,
        )

    def test_aba_antiga_nao_desfaz_retirada_e_reenvio_revisado_preserva_saldo(self):
        dados = self.formulario()
        self.retirar()
        response = self.client.post(self.url, dados)
        self.assertEqual(response.status_code, 409)
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.estoque_atual, 4)
        self.assertEqual(self.equipamento.nome, 'Capacete')
        self.assertEqual(RegistroEPI.objects.count(), 1)
        self.assertContains(response, 'Saldo atualizado: 4', status_code=409)
        self.assertContains(response, 'value="Capacete revisado"', status_code=409)
        dados.update(estoque_atual='4', versao_equipamento=response.context['versao_equipamento'])
        self.assertRedirects(self.client.post(self.url, dados), reverse('catalogo_equipamentos'))
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.nome, 'Capacete revisado')
        self.assertEqual(self.equipamento.estoque_atual, 4)

    def test_conflito_mostra_saldo_zero_sem_reaproveitar_valor_antigo(self):
        dados = self.formulario()
        self.retirar(quantidade=5)
        response = self.client.post(self.url, dados)
        self.assertContains(
            response, 'name="estoque_atual" class="form-control" min="0" value="0"', status_code=409,
        )

    def test_formulario_atual_permite_correcao_legitima_do_estoque(self):
        dados = self.formulario()
        dados['estoque_atual'] = '8'
        self.assertRedirects(self.client.post(self.url, dados), reverse('catalogo_equipamentos'))
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.estoque_atual, 8)

    def test_versao_ausente_adulterada_ou_de_outro_produto_nao_salva(self):
        dados = self.formulario()
        outro = EquipamentoProtecao.objects.create(nome='Luva', estoque_atual=5)
        outra_versao = self.client.get(
            reverse('editar_equipamento', args=[outro.pk]),
        ).context['versao_equipamento']
        for versao in ('', dados['versao_equipamento'] + 'adulterada', outra_versao):
            with self.subTest(versao=versao):
                response = self.client.post(self.url, {**dados, 'versao_equipamento': versao})
                self.assertEqual(response.status_code, 409)
                self.equipamento.refresh_from_db()
                self.assertEqual(self.equipamento.nome, 'Capacete')
                self.assertEqual(self.equipamento.estoque_atual, 5)

    def test_duas_edicoes_nao_sobrescrevem_dados_da_primeira(self):
        primeira_aba = self.formulario()
        segunda_aba = self.formulario()
        self.client.post(self.url, {**primeira_aba, 'fabricante': 'Fabricante novo'})
        self.assertEqual(self.client.post(self.url, segunda_aba).status_code, 409)
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.fabricante, 'Fabricante novo')

    def test_correcao_apos_erro_de_validacao_usa_versao_original(self):
        dados = self.formulario()
        response = self.client.post(self.url, {**dados, 'estoque_atual': '-1'})
        self.assertEqual(response.status_code, 200)
        dados['versao_equipamento'] = response.context['versao_equipamento']
        dados['estoque_atual'] = '6'
        self.assertRedirects(self.client.post(self.url, dados), reverse('catalogo_equipamentos'))
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.estoque_atual, 6)
