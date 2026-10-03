from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from compras.models import Material, RequisicaoCompra, SolicitacaoMaterial
from compras.views import painel_compras
from core.models import PerfilUsuario


class CarregamentoPainelComprasTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser('diretoria-painel')
        PerfilUsuario.objects.create(usuario=self.usuario, perfil='gestor')
        self.request = RequestFactory().get('/compras/')
        self.request.user = self.usuario
        self.request.session = SessionStore()
        self.request._messages = FallbackStorage(self.request)

    def adicionar_requisicao(self, numero):
        material = Material.objects.create(nome=f'Produto do painel {numero}')
        requisicao = RequisicaoCompra.objects.create(
            solicitante='Diretoria', unidade_destino='Matriz', justificativa='Reposição',
        )
        SolicitacaoMaterial.objects.create(
            requisicao=requisicao, material=material, quantidade_solicitada=1, status='pendente',
        )

    def test_consultas_nao_crescem_por_material_ou_requisicao(self):
        self.adicionar_requisicao(0)
        # Aquece permissões e opções da navegação, que não pertencem ao painel.
        painel_compras(self.request)
        with CaptureQueriesContext(connection) as poucas:
            self.assertEqual(painel_compras(self.request).status_code, 200)
        for numero in range(1, 21):
            self.adicionar_requisicao(numero)
        with CaptureQueriesContext(connection) as muitas:
            response = painel_compras(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Produto do painel 20')
        self.assertLessEqual(len(muitas), len(poucas) + 1)
