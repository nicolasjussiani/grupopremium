from django.test import override_settings
from core.approval_test_utils import configurar_aprovadores
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compras.models import EquipamentoManutencao, RequisicaoCompra, SolicitacaoManutencao
from core.models import AprovacaoRegistro, PerfilUsuario


@override_settings(APROVADOR_OPERACIONAL_USERNAME='ceo_premium', APROVADOR_PAGAMENTOS_USERNAME='luiz_teste')
class FluxoManutencaoRequisicaoTests(TestCase):
    def setUp(self):
        configurar_aprovadores(self)
        self.ceo = User.objects.create_user('ceo_premium')
        self.operador = User.objects.create_user('comprador-manutencao')
        PerfilUsuario.objects.create(usuario=self.operador, perfil='compras')
        self.client.force_login(self.operador)
        equipamento = EquipamentoManutencao.objects.create(nome='Lavadora', tipo='maquina')
        response = self.client.post(reverse('nova_solicitacao'), {
            'unidade_destino': 'Matriz', 'justificativa': 'Reparo necessário',
            'manutencao_equipamento': [str(equipamento.pk)],
            'manutencao_problema': ['Motor não liga'],
        })
        self.assertEqual(response.status_code, 302)
        self.requisicao = RequisicaoCompra.objects.get()
        self.manutencao = SolicitacaoManutencao.objects.get()
        self.aprovacao = AprovacaoRegistro.objects.get(modulo='compras')
        self.url = reverse('atualizar_manutencao_requisicao', args=[self.manutencao.pk])
        self.detalhe = reverse('detalhe_requisicao', args=[self.requisicao.pk])

    def aprovar(self):
        self.client.force_login(self.ceo)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[self.aprovacao.pk])).status_code, 302)
        self.client.force_login(self.operador)

    def test_fluxo_completo_aprovar_iniciar_concluir_pela_requisicao(self):
        self.assertNotContains(self.client.get(self.detalhe), self.url)
        self.aprovar()
        self.assertContains(self.client.get(self.detalhe), 'value="iniciar"')
        self.assertRedirects(self.client.post(self.url, {'acao': 'iniciar'}), self.detalhe)
        self.manutencao.refresh_from_db()
        self.assertEqual(self.manutencao.status, 'em_manutencao')
        response = self.client.get(self.detalhe)
        self.assertContains(response, 'value="concluir"')
        self.assertNotContains(response, 'value="iniciar"')
        self.assertRedirects(self.client.post(self.url, {'acao': 'concluir'}), self.detalhe)
        self.manutencao.refresh_from_db()
        self.assertEqual(self.manutencao.status, 'concluida')
        self.assertNotContains(self.client.get(self.detalhe), self.url)

    def test_nao_inicia_antes_da_aprovacao_nem_apos_rejeicao(self):
        for acao in ('iniciar', 'concluir'):
            self.client.post(self.url, {'acao': acao})
            self.manutencao.refresh_from_db()
            self.assertEqual(self.manutencao.status, 'pendente')
        self.client.force_login(self.ceo)
        self.client.post(reverse('rejeitar_registro', args=[self.aprovacao.pk]), {'motivo_rejeicao': 'Revisar'})
        self.client.force_login(self.operador)
        for acao in ('iniciar', 'concluir'):
            self.client.post(self.url, {'acao': acao})
            self.manutencao.refresh_from_db()
            self.assertEqual(self.manutencao.status, 'cancelada')

    def test_nao_pula_etapa_nem_reabre_concluida(self):
        self.aprovar()
        for acao in ('concluir', 'desconhecida'):
            self.client.post(self.url, {'acao': acao})
            self.manutencao.refresh_from_db()
            self.assertEqual(self.manutencao.status, 'aguardando_manutencao')
        self.client.post(self.url, {'acao': 'iniciar'})
        self.manutencao.refresh_from_db()
        inicio_em = self.manutencao.atualizado_em
        self.client.post(self.url, {'acao': 'iniciar'})
        self.manutencao.refresh_from_db()
        self.assertEqual(self.manutencao.status, 'em_manutencao')
        self.assertEqual(self.manutencao.atualizado_em, inicio_em)
        self.client.post(self.url, {'acao': 'concluir'})
        self.manutencao.refresh_from_db()
        conclusao_em = self.manutencao.atualizado_em
        for acao in ('iniciar', 'concluir'):
            self.client.post(self.url, {'acao': acao})
            self.manutencao.refresh_from_db()
            self.assertEqual(self.manutencao.status, 'concluida')
            self.assertEqual(self.manutencao.atualizado_em, conclusao_em)

    def test_acao_exige_post_e_acesso_ao_modulo(self):
        self.aprovar()
        self.assertEqual(self.client.get(self.url).status_code, 405)
        outro_usuario = User.objects.create_user('sem-acesso-compras')
        PerfilUsuario.objects.create(usuario=outro_usuario, perfil='financeiro')
        self.client.force_login(outro_usuario)
        self.assertRedirects(self.client.post(self.url, {'acao': 'iniciar'}), reverse('dashboard'))
        self.manutencao.refresh_from_db()
        self.assertEqual(self.manutencao.status, 'aguardando_manutencao')

    def test_requisicao_com_pedido_tambem_permite_realizar_manutencao(self):
        self.aprovar()
        RequisicaoCompra.objects.filter(pk=self.requisicao.pk).update(status='pedido')
        self.assertContains(self.client.get(self.detalhe), 'value="iniciar"')
        self.client.post(self.url, {'acao': 'iniciar'})
        self.client.post(self.url, {'acao': 'concluir'})
        self.manutencao.refresh_from_db()
        self.assertEqual(self.manutencao.status, 'concluida')
