from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import AprovacaoRegistro, Notificacao, PerfilUsuario
from compras.models import DecisaoItemRequisicao, Material, RequisicaoCompra, SolicitacaoMaterial


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

    def test_painel_mostra_requisicoes_anteriores_as_dez_mais_recentes(self):
        requisicoes = [
            RequisicaoCompra.objects.create(
                solicitante='Comprador Premium',
                unidade_destino=f'Unidade {indice}',
                justificativa='Histórico de compras',
            )
            for indice in range(12)
        ]

        response = self.client.get(reverse('painel_compras'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'requisicoes-scroll')
        self.assertContains(response, requisicoes[0].numero)
        self.assertEqual(len(response.context['requisicoes_recentes']), 12)

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

    def test_valores_informados_aparecem_na_aprovacao_e_na_edicao(self):
        response = self.client.post(reverse('nova_solicitacao'), {
            'material': [str(self.disponivel.pk), str(self.insuficiente.pk)],
            'quantidade_solicitada': ['3', '5'],
            'valor_unitario': ['12,50', '3,20'],
            'unidade_destino': 'Unidade Santos',
            'justificativa': 'Reposição mensal',
        })
        self.assertEqual(response.status_code, 302)
        requisicao = RequisicaoCompra.objects.get()
        self.assertEqual(
            requisicao.itens.get(material=self.disponivel).valor_unitario_estimado,
            Decimal('12.50'),
        )
        aprovacao = AprovacaoRegistro.objects.get(object_id=requisicao.pk, modulo='compras')
        self.client.force_login(self.adriana)
        for rota in ('detalhe_aprovacao', 'detalhe_aprovacao_mobile'):
            with self.subTest(rota=rota):
                detalhe = self.client.get(reverse(rota, args=[aprovacao.pk]))
                self.assertContains(detalhe, 'R$ 12,50')
                self.assertContains(detalhe, 'R$ 37,50')
                self.assertContains(detalhe, 'R$ 53,50')

        self.client.force_login(self.user)
        edicao = self.client.get(reverse('editar_requisicao', args=[requisicao.pk]))
        self.assertContains(edicao, 'value="12,50"')

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

    def _criar_rc_para_decisao(self):
        response = self.client.post(reverse('nova_solicitacao'), {
            'material': [str(self.disponivel.pk), str(self.insuficiente.pk)],
            'quantidade_solicitada': ['3', '5'],
            'unidade_destino': 'Unidade Santos',
            'justificativa': 'Reposição mensal',
        })
        self.assertEqual(response.status_code, 302)
        requisicao = RequisicaoCompra.objects.get()
        aprovacao = AprovacaoRegistro.objects.get(
            object_id=requisicao.pk, modulo='compras', nivel=1,
        )
        return requisicao, aprovacao

    def _decidir_linha(self, aprovacao, item, decisao, observacao=''):
        return self.client.post(
            reverse('decidir_item_requisicao', args=[aprovacao.pk, item.pk]),
            {'decisao': decisao, 'observacao': observacao},
        )

    def test_desaprova_so_uma_linha_e_a_outra_segue_ate_o_ceo(self):
        requisicao, aprovacao = self._criar_rc_para_decisao()
        aprovada = requisicao.itens.get(material=self.disponivel)
        rejeitada = requisicao.itens.get(material=self.insuficiente)
        self.client.force_login(self.adriana)
        detalhe = self.client.get(reverse('detalhe_aprovacao', args=[aprovacao.pk]))
        self.assertContains(detalhe, 'Aprovar esta linha', count=2)
        self.assertEqual(self._decidir_linha(aprovacao, aprovada, 'aprovado').status_code, 302)
        self.assertEqual(self._decidir_linha(aprovacao, rejeitada, 'rejeitado', 'Produto duplicado').status_code, 302)
        rejeitada.refresh_from_db()
        self.assertEqual(rejeitada.status, 'pendente')

        response = self.client.post(reverse('concluir_itens_requisicao', args=[aprovacao.pk]))
        self.assertEqual(response.status_code, 302)
        requisicao.refresh_from_db()
        aprovada.refresh_from_db()
        rejeitada.refresh_from_db()
        self.assertEqual(requisicao.status, 'aguardando_ceo')
        self.assertEqual(aprovada.status, 'pendente')
        self.assertEqual(rejeitada.status, 'cancelado')
        self.assertEqual(rejeitada.obs, 'Produto duplicado')
        segunda = AprovacaoRegistro.objects.get(object_id=requisicao.pk, nivel=2)
        self.client.force_login(self.ceo)
        self.assertContains(
            self.client.get(reverse('detalhe_aprovacao', args=[segunda.pk])),
            'Produto duplicado',
        )
        self.client.post(reverse('aprovar_registro', args=[segunda.pk]))
        requisicao.refresh_from_db()
        aprovada.refresh_from_db()
        rejeitada.refresh_from_db()
        self.disponivel.refresh_from_db()
        self.assertEqual(requisicao.status, 'aprovada')
        self.assertEqual(aprovada.status, 'atendido_interno')
        self.assertEqual(rejeitada.status, 'cancelado')
        self.assertEqual(self.disponivel.quantidade_estoque, Decimal('7.00'))

    def test_todas_as_linhas_desaprovadas_rejeitam_a_rc(self):
        requisicao, aprovacao = self._criar_rc_para_decisao()
        self.client.force_login(self.adriana)
        for item in requisicao.itens.all():
            self._decidir_linha(aprovacao, item, 'rejeitado', 'Não comprar')
        self.client.post(reverse('concluir_itens_requisicao', args=[aprovacao.pk]))
        requisicao.refresh_from_db()
        aprovacao.refresh_from_db()
        self.assertEqual(requisicao.status, 'rejeitada')
        self.assertEqual(aprovacao.status, 'rejeitado')
        self.assertFalse(requisicao.itens.exclude(status='cancelado').exists())
        self.assertFalse(AprovacaoRegistro.objects.filter(object_id=requisicao.pk, nivel=2).exists())

    def test_ceo_pode_desaprovar_uma_linha_sem_processar_seu_estoque(self):
        requisicao, primeira = self._criar_rc_para_decisao()
        self.client.force_login(self.adriana)
        self.client.post(reverse('aprovar_registro', args=[primeira.pk]))
        segunda = AprovacaoRegistro.objects.get(object_id=requisicao.pk, nivel=2)
        aprovada = requisicao.itens.get(material=self.disponivel)
        rejeitada = requisicao.itens.get(material=self.insuficiente)
        self.client.force_login(self.ceo)
        self._decidir_linha(segunda, aprovada, 'aprovado')
        self._decidir_linha(segunda, rejeitada, 'rejeitado', 'Fornecedor sem estoque')
        self.client.post(reverse('concluir_itens_requisicao', args=[segunda.pk]))
        requisicao.refresh_from_db()
        aprovada.refresh_from_db()
        rejeitada.refresh_from_db()
        self.assertEqual(requisicao.status, 'aprovada')
        self.assertEqual(aprovada.status, 'atendido_interno')
        self.assertEqual(rejeitada.status, 'cancelado')

    def test_decisao_parcial_precisa_ser_concluida_e_motivo_e_obrigatorio(self):
        requisicao, aprovacao = self._criar_rc_para_decisao()
        item = requisicao.itens.first()
        self.client.force_login(self.adriana)
        self._decidir_linha(aprovacao, item, 'rejeitado')
        self.assertFalse(DecisaoItemRequisicao.objects.exists())
        self._decidir_linha(aprovacao, item, 'rejeitado', 'Sem necessidade')
        self.client.post(reverse('concluir_itens_requisicao', args=[aprovacao.pk]))
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'pendente')
        self.client.post(reverse('aprovar_registro', args=[aprovacao.pk]))
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'pendente')
        self.client.post(reverse('concluir_itens_requisicao', args=[aprovacao.pk]), {'aprovar_restantes': '1'})
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'aprovado')

    def test_total_selecionado_considera_somente_linhas_aprovadas(self):
        response = self.client.post(reverse('nova_solicitacao'), {
            'material': [str(self.disponivel.pk), str(self.insuficiente.pk)],
            'quantidade_solicitada': ['3', '5'],
            'valor_unitario': ['12,50', '3,20'],
            'unidade_destino': 'Unidade Santos',
            'justificativa': 'Reposição mensal',
        })
        self.assertEqual(response.status_code, 302)
        requisicao = RequisicaoCompra.objects.get()
        aprovacao = AprovacaoRegistro.objects.get(object_id=requisicao.pk, nivel=1)
        self.client.force_login(self.adriana)
        self._decidir_linha(aprovacao, requisicao.itens.get(material=self.disponivel), 'aprovado')
        self._decidir_linha(aprovacao, requisicao.itens.get(material=self.insuficiente), 'rejeitado', 'Sem necessidade')
        detalhe = self.client.get(reverse('detalhe_aprovacao', args=[aprovacao.pk]))
        self.assertContains(detalhe, 'Total selecionado:')
        self.assertContains(detalhe, 'R$ 37,50')
