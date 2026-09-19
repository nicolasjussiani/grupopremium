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
