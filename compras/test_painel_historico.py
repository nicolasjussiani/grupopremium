from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from compras.models import RequisicaoCompra
from core.models import PerfilUsuario


class HistoricoRequisicoesTests(TestCase):
    def test_painel_exibe_requisicoes_anteriores_as_dez_mais_recentes(self):
        usuario = User.objects.create_user(username='comprador-historico')
        PerfilUsuario.objects.create(usuario=usuario, perfil='compras')
        self.client.force_login(usuario)
        requisicoes = []
        for indice in range(12):
            requisicao = RequisicaoCompra.objects.create(
                solicitante='Comprador',
                solicitante_usuario=usuario,
                unidade_destino='Sede',
                justificativa='Reposição',
            )
            RequisicaoCompra.objects.filter(pk=requisicao.pk).update(
                criado_em=timezone.now() - timedelta(days=indice)
            )
            requisicoes.append(requisicao)

        response = self.client.get(reverse('painel_compras'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [rc.pk for rc in response.context['requisicoes_recentes']],
            [rc.pk for rc in requisicoes],
        )
        self.assertContains(response, requisicoes[-1].numero)
        self.assertContains(
            response, reverse('detalhe_requisicao', args=[requisicoes[-1].pk])
        )
