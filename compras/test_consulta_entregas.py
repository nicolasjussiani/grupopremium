from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from compras.models import Material, RequisicaoCompra, SolicitacaoMaterial
from core.forms import UsuarioERPForm
from core.models import PerfilUsuario


class ConsultaEntregasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('eric', password='Senha-teste-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='entregas_consulta')
        self.client.force_login(self.user)

    def item(self, nome, status_rc='aprovada', status_item='atendido_interno', unidade='Unidade A'):
        rc = RequisicaoCompra.objects.create(
            solicitante='Solicitante', unidade_destino=unidade,
            justificativa='Dado interno que não deve aparecer', status=status_rc,
        )
        return SolicitacaoMaterial.objects.create(
            requisicao=rc, material=Material.objects.create(nome=nome, preco_unitario=9876),
            quantidade_solicitada=3, status=status_item,
        )

    def test_consulta_apenas_rcs_aprovadas_sem_dados_financeiros(self):
        self.item('Produto liberado')
        self.item('Produto a comprar', status_item='compra_externa')
        self.item('Produto pendente Adriana', status_rc='aguardando_adriana')
        self.item('Produto pendente CEO', status_rc='aguardando_ceo')
        self.item('Produto rejeitado', status_rc='rejeitada')
        self.item('Produto cancelado', status_item='cancelado')
        response = self.client.get(reverse('consulta_entregas'))
        self.assertContains(response, 'Produto liberado')
        self.assertContains(response, 'Produto a comprar')
        for text in ('Produto pendente', 'Produto rejeitado', 'Produto cancelado', '9876', 'Dado interno'):
            self.assertNotContains(response, text)

    def test_filtro_por_unidade_e_estado_vazio(self):
        self.item('Produto A')
        self.item('Produto B', unidade='Unidade B')
        response = self.client.get(reverse('consulta_entregas'), {'unidade': 'Unidade B'})
        self.assertContains(response, 'Produto B')
        self.assertNotContains(response, 'Produto A')
        response = self.client.get(reverse('consulta_entregas'), {'unidade': 'Inexistente'})
        self.assertContains(response, 'Nenhum material liberado')

    def test_login_sem_email_ignora_next_e_sai(self):
        self.client.logout()
        response = self.client.post(reverse('login') + '?next=/financeiro/', {
            'username': 'eric', 'password': 'Senha-teste-123',
        })
        self.assertRedirects(response, reverse('consulta_entregas'))
        self.assertRedirects(self.client.get('/'), reverse('consulta_entregas'))
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))

    def test_bloqueia_outros_modulos_e_escrita_mesmo_com_grupo_admin(self):
        self.user.groups.add(Group.objects.create(name='Admin_Global'))
        item = self.item('Produto protegido')
        urls = [
            '/admin/', '/financeiro/', '/admissional/', '/compras/', '/sesmet/',
            '/usuarios/', '/cadastros/', '/arquivo-central/', '/assistente/',
            '/api/notificacoes/', '/api/uploads/presign/', '/mobile/', '/aprovacoes/',
            reverse('detalhe_requisicao', args=[item.requisicao_id]),
        ]
        for url in urls:
            for method in ('get', 'post'):
                with self.subTest(url=url, method=method):
                    self.assertEqual(getattr(self.client, method)(url).status_code, 403)
        for method in ('post', 'put', 'patch', 'delete'):
            self.assertEqual(getattr(self.client, method)(reverse('consulta_entregas')).status_code, 403)
        item.refresh_from_db()
        self.assertEqual(item.status, 'atendido_interno')

    def test_acesso_exige_autenticacao_e_perfil(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('consulta_entregas')).status_code, 302)
        self.user.perfil.perfil = 'operacional'
        self.user.perfil.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('consulta_entregas')).status_code, 403)

    def test_cadastro_sem_email_e_sem_permissoes_adicionais(self):
        data = {
            'username': 'entregador', 'first_name': 'Eric', 'last_name': 'Entrega',
            'email': '', 'perfil': 'entregas_consulta', 'marca': 'matriz', 'unidade': 'Matriz',
            'is_active': True, 'password1': 'Senha-teste-123', 'password2': 'Senha-teste-123',
        }
        form = UsuarioERPForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, '')
        self.assertEqual(user.perfil.perfil, 'entregas_consulta')
        self.assertFalse(user.groups.exists())
        form = UsuarioERPForm({**data, 'username': 'outro', 'acesso_financeiro': True})
        self.assertFalse(form.is_valid())
