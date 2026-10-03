from decimal import Decimal
import re
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.models import ItemPedidoCompra, Material, PedidoCompra, RequisicaoCompra, SolicitacaoMaterial
from core.models import AprovacaoRegistro, PerfilUsuario


class SelecaoPedidosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('comprador-selecao')
        PerfilUsuario.objects.create(usuario=self.user, perfil='compras')
        adriana = User.objects.create_user('adriana')
        PerfilUsuario.objects.create(usuario=adriana, perfil='gestor')
        self.client.force_login(self.user)
        self.requisicao = RequisicaoCompra.objects.create(
            solicitante='Comprador', solicitante_usuario=self.user,
            unidade_destino='Matriz', justificativa='Reposição', status='aprovada',
        )
        self.itens = [self.item('Silicone', '2.50'), self.item('Shampoo', '3')]
        self.url = reverse('criar_pedidos_requisicao', args=[self.requisicao.pk])
        self.detalhe = reverse('detalhe_requisicao', args=[self.requisicao.pk])

    def item(self, nome, quantidade='1', **kwargs):
        return SolicitacaoMaterial.objects.create(
            requisicao=kwargs.pop('requisicao', self.requisicao),
            material=Material.objects.create(nome=nome),
            quantidade_solicitada=quantidade,
            status=kwargs.pop('status', 'compra_externa'), **kwargs,
        )

    def dados(self, itens=None, **kwargs):
        dados = {
            'itens': [item.pk for item in (self.itens if itens is None else itens)],
            'fornecedor': 'Fornecedor de limpeza', 'cnpj_fornecedor': '',
            'prazo_entrega': '2026-10-20',
            **{f'valor_unitario_{item.pk}': '10.01' for item in self.itens},
        }
        dados.update(kwargs)
        return dados

    def test_selecao_aparece_so_para_itens_disponiveis(self):
        interno = self.item('Interno', status='atendido_interno')
        ocupado = self.item('Já comprado')
        PedidoCompra.objects.create(
            solicitacao=ocupado, fornecedor='Anterior', valor_unitario=1,
            valor_total=1, status='aguardando_aprovacao',
        )
        response = self.client.get(self.detalhe)
        self.assertContains(response, 'Selecionar todos disponíveis')
        self.assertContains(response, 'Criar pedido com os itens selecionados')
        for item in self.itens:
            self.assertContains(response, f'data-purchase-item="{item.pk}"', count=2)
        for item in [interno, ocupado]:
            self.assertNotContains(response, f'data-purchase-item="{item.pk}"')

    def test_get_mostra_apenas_selecionados_e_nao_cria_pedidos(self):
        response = self.client.get(self.url, {'itens': [self.itens[0].pk]})
        self.assertContains(response, 'Silicone')
        self.assertNotContains(response, 'Shampoo')
        self.assertContains(response, 'data-quantity="2.50"')
        self.assertEqual(len(re.findall(r'<input\b[^>]*name="fornecedor"', response.content.decode())), 1)
        self.assertContains(response, 'único pedido')
        self.assertEqual(PedidoCompra.objects.count(), 0)

    def test_cria_so_linhas_selecionadas(self):
        response = self.client.post(self.url, self.dados(itens=[self.itens[0]]))
        pedido = PedidoCompra.objects.get()
        self.assertRedirects(response, pedido.get_absolute_url())
        self.assertEqual(pedido.requisicao, self.requisicao)
        self.assertEqual(pedido.itens.get().solicitacao, self.itens[0])
        self.assertEqual(pedido.valor_total, Decimal('25.03'))
        self.assertEqual(pedido.status, 'pedido_emitido')
        self.assertEqual(AprovacaoRegistro.objects.count(), 0)
        self.itens[0].refresh_from_db()
        self.itens[1].refresh_from_db()
        self.requisicao.refresh_from_db()
        self.assertEqual(self.itens[0].status, 'aguardando_entrega')
        self.assertEqual(self.itens[1].status, 'compra_externa')
        self.assertEqual(self.requisicao.status, 'pedido')
        self.assertContains(self.client.get(self.detalhe), f'data-purchase-item="{self.itens[1].pk}"')

    def test_cria_todas_selecionadas_com_precos_distintos_e_sem_duplicar_ids(self):
        response = self.client.post(self.url, self.dados(
            itens=self.itens + [self.itens[0]],
            **{f'valor_unitario_{self.itens[1].pk}': '20,00'},
        ))
        pedido = PedidoCompra.objects.get()
        self.assertRedirects(response, pedido.get_absolute_url())
        self.assertEqual([linha.valor_total for linha in pedido.itens.all()], [Decimal('25.03'), Decimal('60.00')])
        self.assertEqual(pedido.valor_total, Decimal('85.03'))
        self.assertEqual(AprovacaoRegistro.objects.count(), 0)
        self.assertEqual(pedido.cnpj_fornecedor, '')
        self.assertNotContains(self.client.get(self.detalhe), 'selectedOrdersForm')
        painel = self.client.get(reverse('painel_compras'))
        self.assertEqual(len(painel.context['pedidos']), 1)
        self.assertContains(painel, 'Silicone, Shampoo')
        self.assertContains(painel, '85,03')
        for item in self.itens:
            detalhe = self.client.get(reverse('detalhe_solicitacao', args=[item.pk]))
            self.assertContains(detalhe, pedido.numero_pedido)
            self.assertContains(detalhe, pedido.get_absolute_url())

    def test_reenvio_nao_gera_pedidos_duplicados(self):
        self.client.post(self.url, self.dados())
        response = self.client.post(self.url, self.dados())
        self.assertRedirects(response, self.detalhe)
        self.assertEqual(PedidoCompra.objects.count(), 1)
        self.assertEqual(ItemPedidoCompra.objects.count(), 2)
        self.assertEqual(AprovacaoRegistro.objects.count(), 0)

    def test_selecao_vazia_ou_invalida(self):
        for ids in [[], ['abc'], ['999999'], ['999999999999999999999999999']]:
            with self.subTest(ids=ids):
                self.assertRedirects(self.client.post(self.url, self.dados() | {'itens': ids}), self.detalhe)
        self.assertEqual(PedidoCompra.objects.count(), 0)

    def test_nao_aceita_item_de_outra_requisicao_ou_do_estoque(self):
        outra = RequisicaoCompra.objects.create(
            solicitante='Outro', unidade_destino='Filial', justificativa='Outro', status='aprovada',
        )
        externo = self.item('Outra requisição', requisicao=outra)
        interno = self.item('Estoque', status='atendido_interno')
        for invalido in [externo, interno]:
            response = self.client.post(self.url, self.dados(itens=[self.itens[0], invalido]))
            self.assertRedirects(response, self.detalhe)
        self.assertEqual(PedidoCompra.objects.count(), 0)

    def test_nao_aceita_requisicao_sem_aprovacao(self):
        self.requisicao.status = 'aguardando_ceo'
        self.requisicao.save()
        self.assertNotContains(self.client.get(self.detalhe), 'selectedOrdersForm')
        self.assertRedirects(self.client.post(self.url, self.dados()), self.detalhe)
        self.assertEqual(PedidoCompra.objects.count(), 0)

    def test_valor_invalido_preserva_formulario_sem_criar_pedidos(self):
        for valor in ['', '0', '-5', 'NaN', 'Infinity', 'abc', '9999999999999999999']:
            with self.subTest(valor=valor):
                response = self.client.post(self.url, self.dados(
                    **{f'valor_unitario_{self.itens[1].pk}': valor},
                ))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Fornecedor de limpeza')
                self.assertContains(response, 'value="10.01"')
                self.assertEqual(PedidoCompra.objects.count(), 0)

    def test_falha_no_segundo_item_desfaz_pedido_itens_e_status(self):
        salvar = ItemPedidoCompra.save
        with patch.object(ItemPedidoCompra, 'save', autospec=True) as mock:
            def salvar_pedido(pedido, *args, **kwargs):
                if mock.call_count == 2:
                    raise IntegrityError('Falha de teste')
                return salvar(pedido, *args, **kwargs)
            mock.side_effect = salvar_pedido
            response = self.client.post(self.url, self.dados())
        self.assertContains(response, 'Um dos produtos já possui pedido ativo.')
        self.assertEqual(PedidoCompra.objects.count(), 0)
        self.assertEqual(ItemPedidoCompra.objects.count(), 0)
        self.assertEqual(AprovacaoRegistro.objects.count(), 0)
        self.requisicao.refresh_from_db()
        self.assertEqual(self.requisicao.status, 'aprovada')
        self.assertEqual(set(self.requisicao.itens.values_list('status', flat=True)), {'compra_externa'})

    def test_cria_pedidos_restantes_de_requisicao_com_status_pedido(self):
        self.client.post(self.url, self.dados(itens=[self.itens[0]]))
        response = self.client.post(self.url, self.dados(itens=[self.itens[1]]))
        self.assertRedirects(response, PedidoCompra.objects.first().get_absolute_url())
        self.assertEqual(PedidoCompra.objects.count(), 2)
        self.assertEqual(set(self.requisicao.itens.values_list('status', flat=True)), {'aguardando_entrega'})

    def test_pedido_reprovado_permite_nova_compra(self):
        PedidoCompra.objects.create(
            solicitacao=self.itens[0], fornecedor='Anterior', valor_unitario=1,
            valor_total=1, status='reprovado',
        )
        response = self.client.post(self.url, self.dados())
        pedido = PedidoCompra.objects.exclude(status='reprovado').get()
        self.assertRedirects(response, pedido.get_absolute_url())
        self.assertEqual(pedido.itens.count(), 2)

    def test_entrega_parcial_nao_conclui_pedido_antes_do_ultimo_item(self):
        self.client.post(self.url, self.dados())
        pedido = PedidoCompra.objects.get()
        self.client.post(reverse('confirmar_entrega', args=[self.itens[0].pk]))
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'pedido_emitido')
        self.assertEqual(pedido.status_entrega, 'Entrega parcial')
        self.assertContains(self.client.get(pedido.get_absolute_url()), 'Entrega parcial')
        self.client.post(reverse('confirmar_entrega', args=[self.itens[1].pk]))
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'concluido')
        self.assertEqual(pedido.status_entrega, 'Entregue')
        self.assertEqual(PedidoCompra.objects.count(), 1)
        self.assertEqual(pedido.valor_total, Decimal('55.06'))

    def test_cnpj_prazo_e_observacoes_sao_do_pedido_inteiro(self):
        self.client.post(self.url, self.dados(cnpj_fornecedor='12345678000199', obs='Entregar pela manhã'))
        pedido = PedidoCompra.objects.get()
        detalhe = self.client.get(pedido.get_absolute_url())
        self.assertContains(detalhe, 'Fornecedor de limpeza')
        self.assertContains(detalhe, 'Entregar pela manhã')
        self.assertContains(detalhe, '20/10/2026')
        self.assertEqual(len(re.findall(r'<input\b[^>]*name="cnpj_fornecedor"', detalhe.content.decode())), 1)
        self.assertEqual(pedido.cnpj_fornecedor, '12.345.678/0001-99')
        self.assertRedirects(self.client.post(reverse('atualizar_cnpj_pedido', args=[pedido.pk]), {
            'cnpj_fornecedor': '98765432000199',
        }), pedido.get_absolute_url())
        pedido.refresh_from_db()
        self.assertEqual(pedido.cnpj_fornecedor, '98.765.432/0001-99')
        self.assertEqual(pedido.valor_total, Decimal('55.06'))

    def test_item_agrupado_nao_pode_ser_comprado_individualmente(self):
        self.client.post(self.url, self.dados())
        SolicitacaoMaterial.objects.filter(pk=self.itens[1].pk).update(status='compra_externa')
        self.client.post(reverse('criar_pedido', args=[self.itens[1].pk]), {
            'fornecedor': 'Outro', 'valor_unitario': '12',
        })
        self.assertEqual(PedidoCompra.objects.count(), 1)
        self.assertNotContains(self.client.get(self.detalhe), 'selectedOrdersForm')

    def test_dados_gerais_invalidos_e_total_excedido_nao_criam_pedido(self):
        for dados in [self.dados(fornecedor=' '), self.dados(cnpj_fornecedor='123'),
                      self.dados(prazo_entrega='data-invalida')]:
            self.assertEqual(self.client.post(self.url, dados).status_code, 200)
            self.assertEqual(PedidoCompra.objects.count(), 0)
        SolicitacaoMaterial.objects.filter(pk=self.itens[0].pk).update(quantidade_solicitada='99999999.99')
        self.assertEqual(self.client.post(self.url, self.dados(
            **{f'valor_unitario_{self.itens[0].pk}': '99999999.99'},
        )).status_code, 200)
        self.assertEqual(PedidoCompra.objects.count(), 0)

    def test_reprovacao_agrupada_libera_todos_os_itens_para_novo_pedido(self):
        self.client.post(self.url, self.dados())
        pedido = PedidoCompra.objects.get()
        pedido.status = 'aguardando_aprovacao'
        pedido.save()
        pedido.reprovar('Revisar cotação')
        self.assertFalse(pedido.itens.filter(ativo=True).exists())
        self.client.post(self.url, self.dados())
        self.assertEqual(PedidoCompra.objects.exclude(status='reprovado').count(), 1)
        self.assertEqual(ItemPedidoCompra.objects.filter(ativo=True).count(), 2)

    def test_diretoria_mostra_um_processo_para_todos_os_itens_do_pedido(self):
        self.client.post(self.url, self.dados())
        pedido = PedidoCompra.objects.get()
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        response = self.client.get(reverse('painel_sla'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Silicone, Shampoo - Fornecedor de limpeza')
        self.assertContains(response, pedido.get_absolute_url())

    def test_detalhe_de_pedido_individual_antigo_preserva_valores(self):
        pedido = PedidoCompra.objects.create(
            solicitacao=self.itens[0], fornecedor='Fornecedor antigo',
            valor_unitario=Decimal('10.01'), valor_total=Decimal('25.03'), status='pedido_emitido',
        )
        response = self.client.get(pedido.get_absolute_url())
        self.assertContains(response, 'Fornecedor antigo')
        self.assertContains(response, 'Silicone')
        self.assertContains(response, '25,03')
        self.assertNotContains(response, 'Shampoo')

    @override_settings(MIDDLEWARE=[
        middleware for middleware in settings.MIDDLEWARE
        if middleware != 'core.middleware.AcessoModuloMiddleware'
    ])
    def test_usuario_sem_permissao_nao_pode_criar_pedidos(self):
        usuario = User.objects.create_user('consulta-selecao')
        PerfilUsuario.objects.create(usuario=usuario, perfil='colaborador')
        usuario.user_permissions.add(Permission.objects.get(codename='view_material'))
        self.client.force_login(usuario)
        self.assertNotContains(self.client.get(self.detalhe), 'selectedOrdersForm')
        self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)
        self.assertEqual(PedidoCompra.objects.count(), 0)
