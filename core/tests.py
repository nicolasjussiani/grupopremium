from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from core.models import AprovacaoRegistro
from administrativo.models import DemandaAdministrativa
from compras.models import Material, RequisicaoCompra, SolicitacaoMaterial

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
        aprovacao = AprovacaoRegistro.criar_para(
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
        aprovacao = AprovacaoRegistro.criar_para(
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


class DetalheAprovacaoCompraTest(TestCase):
    def setUp(self):
        self.aprovador = User.objects.create_superuser('aprovador_compras', password='senha-123')
        self.client.force_login(self.aprovador)
        requisicao = RequisicaoCompra.objects.create(
            solicitante='Solicitante', unidade_destino='Santos', justificativa='Reposição'
        )
        material = Material.objects.create(
            nome='Produto da RC', descricao='Modelo azul', unidade_medida='cx'
        )
        SolicitacaoMaterial.objects.create(
            material=material, requisicao=requisicao, quantidade_solicitada=3,
            solicitante='Solicitante', unidade_destino='Santos', justificativa='Reposição'
        )
        self.aprovacao = AprovacaoRegistro.criar_para(
            objeto=requisicao, titulo='RC de Santos', modulo='compras', nivel=1
        )

    def test_produtos_aparecem_nos_detalhes_desktop_e_mobile(self):
        for rota in ('detalhe_aprovacao', 'detalhe_aprovacao_mobile'):
            with self.subTest(rota=rota):
                response = self.client.get(reverse(rota, args=[self.aprovacao.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Produto da RC')
                self.assertContains(response, 'Modelo azul')
                self.assertContains(response, '3,00')
                self.assertContains(response, 'Valor não informado nesta RC')
                self.assertContains(response, 'Total indisponível')

    def test_lista_de_aprovacoes_monta_rotas_com_id_antes_da_acao(self):
        response = self.client.get(reverse('aprovacoes_pendentes'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'/aprovacoes/0/aprovar/')
        self.assertContains(response, f'/aprovacoes/0/rejeitar/')
        self.assertNotContains(response, '/aprovacoes/aprovar/0/')
        self.assertNotContains(response, '/aprovacoes/rejeitar/0/')

    def test_detalhe_oferece_observacao_e_mostra_a_etapa_anterior(self):
        detalhe = self.client.get(reverse('detalhe_aprovacao', args=[self.aprovacao.pk]))
        self.assertContains(detalhe, 'name="comentario"')
        self.assertContains(detalhe, 'name="motivo_rejeicao"')
        self.assertContains(detalhe, 'A decisão vale para a RC inteira')

        self.aprovacao.status = 'aprovado'
        self.aprovacao.aprovado_por = self.aprovador
        self.aprovacao.comentario = 'Solicitar troca da cera na próxima compra.'
        self.aprovacao.save(update_fields=['status', 'aprovado_por', 'comentario'])
        proxima = AprovacaoRegistro.criar_para(
            objeto=self.aprovacao.objeto,
            titulo='RC de Santos', modulo='compras', nivel=2,
        )
        for rota in ('detalhe_aprovacao', 'detalhe_aprovacao_mobile'):
            with self.subTest(rota=rota):
                response = self.client.get(reverse(rota, args=[proxima.pk]))
                self.assertContains(response, 'Solicitar troca da cera na próxima compra.')
