from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compras.models import Material, PedidoCompra, SolicitacaoMaterial
from core.models import PerfilUsuario
from sesmet.models import EquipamentoProtecao


class AutomaticCodeTests(TestCase):
    def test_material_recebe_codigo_automatico(self):
        material = Material.objects.create(nome='Luva para estoque')
        self.assertEqual(material.codigo, f'MAT-{material.pk:06d}')

    def test_epi_recebe_codigo_interno_sem_alterar_ca(self):
        epi = EquipamentoProtecao.objects.create(nome='Capacete', numero_ca='CA-OFICIAL')
        self.assertEqual(epi.codigo, f'EPI-{epi.pk:06d}')
        self.assertEqual(epi.numero_ca, 'CA-OFICIAL')

    def test_solicitacao_e_pedido_possuem_numeros_automaticos(self):
        material = Material.objects.create(nome='Material')
        solicitacao = SolicitacaoMaterial.objects.create(
            material=material,
            quantidade_solicitada=1,
            solicitante='Teste',
            unidade_destino='Matriz',
            justificativa='Reposicao',
        )
        pedido = PedidoCompra.objects.create(
            solicitacao=solicitacao,
            fornecedor='Fornecedor',
            valor_unitario=10,
            valor_total=10,
        )
        self.assertEqual(solicitacao.numero, f'SOL-{solicitacao.pk:06d}')
        self.assertEqual(pedido.numero_pedido, f'PC-{pedido.pk:06d}')


class MaterialViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('almoxarife', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='estoque_compras')
        self.client.force_login(self.user)

    def test_cadastra_material_sem_informar_codigo(self):
        response = self.client.post(reverse('novo_material'), {
            'nome': 'Produto de limpeza',
            'descricao': '',
            'categoria': 'limpeza',
            'unidade_medida': 'un',
            'quantidade_estoque': '10',
            'estoque_minimo': '2',
            'preco_unitario': '',
            'fornecedor_preferencial': '',
            'localizacao': 'A1',
        })
        self.assertRedirects(response, reverse('lista_materiais'))
        self.assertRegex(Material.objects.get(nome='Produto de limpeza').codigo, r'^MAT-\d{6}$')
