from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import AprovacaoRegistro, Notificacao, PerfilUsuario
from compras.models import Material, RequisicaoCompra, SolicitacaoMaterial


class RequisicaoComVariosProdutosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='comprador-multiplo',
            password='senha-forte-123',
            first_name='Comprador',
            last_name='Premium',
        )
        PerfilUsuario.objects.create(usuario=self.user, perfil='compras')
        self.adriana = User.objects.create_user('adriana', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.adriana, perfil='gestor')
        self.ceo = User.objects.create_superuser('ceo_premium', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.ceo, perfil='gestor')
        self.client.force_login(self.user)
        self.disponivel = Material.objects.create(
            nome='Produto disponível',
            quantidade_estoque='10.00',
            estoque_minimo='2.00',
        )
        self.insuficiente = Material.objects.create(
            nome='Produto para compra',
            quantidade_estoque='1.00',
            estoque_minimo='2.00',
        )

    def aprovar_requisicao(self, requisicao):
        nivel_adriana = AprovacaoRegistro.objects.get(
            object_id=requisicao.pk, nivel=1, destinatario=self.adriana
        )
        self.client.force_login(self.adriana)
        self.client.post(reverse('aprovar_registro', args=[nivel_adriana.pk]))
        nivel_ceo = AprovacaoRegistro.objects.get(
            object_id=requisicao.pk, nivel=2, destinatario=self.ceo
        )
        self.client.force_login(self.ceo)
        self.client.post(reverse('aprovar_registro', args=[nivel_ceo.pk]))
        self.client.force_login(self.user)

    def test_abre_formulario_de_nova_requisicao(self):
        response = self.client.get(reverse('nova_solicitacao'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="valor_unitario"')
        self.assertNotContains(response, 'debug_traceback')

    def test_cria_uma_requisicao_com_varios_produtos_na_mesma_unidade(self):
        response = self.client.post(reverse('nova_solicitacao'), {
            'material': [str(self.disponivel.pk), str(self.insuficiente.pk)],
            'quantidade_solicitada': ['3', '5'],
            'unidade_destino': 'Unidade Santos',
            'justificativa': 'Reposição mensal da unidade',
        })

        requisicao = RequisicaoCompra.objects.get()
        self.assertRedirects(
            response,
            reverse('detalhe_requisicao', args=[requisicao.pk]),
        )
        self.assertEqual(requisicao.itens.count(), 2)
        self.assertEqual(requisicao.status, 'aguardando_adriana')
        self.assertTrue(AprovacaoRegistro.objects.filter(
            object_id=requisicao.pk, nivel=1, destinatario=self.adriana,
            status='pendente',
        ).exists())
        self.assertTrue(Notificacao.objects.filter(
            destinatario=self.adriana, modulo='compras'
        ).exists())
        self.disponivel.refresh_from_db()
        self.assertEqual(self.disponivel.quantidade_estoque, Decimal('10.00'))

        self.aprovar_requisicao(requisicao)
        requisicao.refresh_from_db()
        self.assertEqual(requisicao.status, 'aprovada')
        self.assertEqual(
            set(requisicao.itens.values_list('unidade_destino', flat=True)),
            {'Unidade Santos'},
        )
        self.assertEqual(
            requisicao.itens.get(material=self.disponivel).status,
            'atendido_interno',
        )
        self.assertEqual(
            requisicao.itens.get(material=self.insuficiente).status,
            'compra_externa',
        )
        self.disponivel.refresh_from_db()
        self.insuficiente.refresh_from_db()
        self.assertEqual(self.disponivel.quantidade_estoque, Decimal('7.00'))
        self.assertEqual(self.insuficiente.quantidade_estoque, Decimal('1.00'))

    def test_impede_produto_repetido_sem_criar_dados_ou_baixar_estoque(self):
        response = self.client.post(reverse('nova_solicitacao'), {
            'material': [str(self.disponivel.pk), str(self.disponivel.pk)],
            'quantidade_solicitada': ['2', '3'],
            'unidade_destino': 'Matriz',
            'justificativa': 'Teste de duplicidade',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'O mesmo produto não pode ser repetido')
        self.assertFalse(RequisicaoCompra.objects.exists())
        self.assertFalse(SolicitacaoMaterial.objects.exists())
        self.disponivel.refresh_from_db()
        self.assertEqual(self.disponivel.quantidade_estoque, Decimal('10.00'))

    def test_formato_antigo_com_um_produto_continua_funcionando(self):
        response = self.client.post(reverse('nova_solicitacao'), {
            'material': str(self.insuficiente.pk),
            'quantidade_solicitada': '4',
            'unidade_destino': 'Matriz',
            'justificativa': 'Compatibilidade com formulário anterior',
        })

        self.assertEqual(response.status_code, 302)
        requisicao = RequisicaoCompra.objects.get()
        self.assertEqual(requisicao.itens.count(), 1)
        self.assertEqual(requisicao.itens.get().status, 'pendente')
        self.aprovar_requisicao(requisicao)
        self.assertEqual(requisicao.itens.get().status, 'compra_externa')

    def test_item_agrupado_sempre_herda_a_unidade_da_requisicao(self):
        requisicao = RequisicaoCompra.objects.create(
            solicitante='Comprador Premium',
            solicitante_usuario=self.user,
            unidade_destino='Unidade única',
            justificativa='Compra agrupada',
        )

        item = SolicitacaoMaterial.objects.create(
            requisicao=requisicao,
            material=self.insuficiente,
            quantidade_solicitada='2',
            solicitante='Outro nome',
            unidade_destino='Outra unidade',
            justificativa='Outra justificativa',
        )

        self.assertEqual(item.unidade_destino, 'Unidade única')
        self.assertEqual(item.justificativa, 'Compra agrupada')
        self.assertEqual(item.solicitante, 'Comprador Premium')

    def test_detalhe_agrupado_exibe_todos_os_produtos(self):
        requisicao = RequisicaoCompra.objects.create(
            solicitante='Comprador Premium',
            solicitante_usuario=self.user,
            unidade_destino='Unidade Santos',
            justificativa='Compra agrupada',
        )
        for material in (self.disponivel, self.insuficiente):
            SolicitacaoMaterial.objects.create(
                requisicao=requisicao,
                material=material,
                quantidade_solicitada='2',
                solicitante=requisicao.solicitante,
                unidade_destino=requisicao.unidade_destino,
                justificativa=requisicao.justificativa,
                status='compra_externa',
            )

        response = self.client.get(
            reverse('detalhe_requisicao', args=[requisicao.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.disponivel.nome)
        self.assertContains(response, self.insuficiente.nome)
        self.assertContains(response, 'Unidade Santos')
