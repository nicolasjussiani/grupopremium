from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from core.models import AprovacaoRegistro
from administrativo.models import DemandaAdministrativa

class AprovacaoProcessoTest(TestCase):
    def setUp(self):
        # Cria usuários
        self.solicitante = User.objects.create_user(username='solicitante', password='123')
        self.aprovador = User.objects.create_user(username='aprovador', password='123')
        
        # Cria grupo de aprovação e adiciona o aprovador
        grupo, _ = Group.objects.get_or_create(name='Administrativo_Gestor')
        self.aprovador.groups.add(grupo)
        
        # Inicia cliente HTTP
        self.client = Client()

    def test_fluxo_aprovacao_administrativo(self):
        # 1. Cria um registro no módulo Administrativo
        demanda = DemandaAdministrativa.objects.create(
            tipo='apoio_operacional',
            titulo='Teste de Demanda',
            descricao='Precisamos de cadeiras novas.',
            requisitante='João',
            requisitante_usuario=self.solicitante,
            status='recebida'
        )

        # 2. Cria a aprovação (normalmente acionada por um gatilho na view do módulo)
        aprovacao = AprovacaoRegistro.criar_aprovacao(
            objeto=demanda,
            modulo='administrativo',
            titulo=f'Aprovação da demanda: {demanda.titulo}',
            solicitado_por=self.solicitante,
            nivel=1
        )

        self.assertEqual(aprovacao.status, 'pendente')

        # 3. Faz login como aprovador
        self.client.login(username='aprovador', password='123')

        # 4. Faz requisição POST para aprovar o registro
        url = reverse('aprovar_registro', args=[aprovacao.pk])
        response = self.client.post(url, {
            'comentario': 'Aprovado conforme política interna.'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

        # 5. Verifica se o registro de aprovação foi atualizado
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'aprovado')
        self.assertEqual(aprovacao.aprovado_por, self.aprovador)
        self.assertEqual(aprovacao.comentario, 'Aprovado conforme política interna.')

        # 6. Verifica o callback: O status da demanda deve ter mudado para 'em_execucao'
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, 'em_execucao')

    def test_fluxo_rejeicao_administrativo(self):
        # Cria demanda e aprovação
        demanda = DemandaAdministrativa.objects.create(
            tipo='pagamentos',
            titulo='Teste Rejeição',
            descricao='Pagamento não autorizado.',
            requisitante='Maria',
            requisitante_usuario=self.solicitante,
            status='recebida'
        )
        aprovacao = AprovacaoRegistro.criar_aprovacao(
            objeto=demanda, modulo='administrativo', titulo='Aprovação Rejeitada', solicitado_por=self.solicitante, nivel=1
        )

        # Faz login como aprovador
        self.client.login(username='aprovador', password='123')

        # Requisição POST para rejeitar o registro
        url = reverse('rejeitar_registro', args=[aprovacao.pk])
        response = self.client.post(url, {
            'motivo_rejeicao': 'Falta orçamento.'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)

        # Verifica aprovação
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'rejeitado')
        self.assertEqual(aprovacao.motivo_rejeicao, 'Falta orçamento.')

        # Verifica callback
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, 'informacoes_incompletas')
