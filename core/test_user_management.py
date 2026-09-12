from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import PerfilUsuario


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin-usuarios', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.admin, perfil='admin')
        self.client.force_login(self.admin)

    def test_admin_cria_usuario_com_perfil_e_grupo(self):
        call_command('criar_grupos', stdout=StringIO())
        response = self.client.post(reverse('novo_usuario'), {
            'username': 'igor.gama',
            'first_name': 'Igor',
            'last_name': 'Gama Rodrigues',
            'email': '',
            'telefone': '',
            'perfil': 'estoque_compras',
            'marca': 'eco_premium',
            'unidade': 'Matriz',
            'is_active': 'on',
            'password1': 'Senha-temporaria-123',
            'password2': 'Senha-temporaria-123',
        })

        self.assertRedirects(response, reverse('lista_usuarios'))
        user = User.objects.get(username='igor.gama')
        self.assertEqual(user.get_full_name(), 'Igor Gama Rodrigues')
        self.assertEqual(user.perfil.perfil, 'estoque_compras')
        self.assertTrue(user.groups.filter(name='Estoque_EPI_Compras').exists())

    def test_admin_cria_usuario_rh_com_permissoes_de_epi(self):
        call_command('criar_grupos', stdout=StringIO())
        response = self.client.post(reverse('novo_usuario'), {
            'username': 'yasmin.rh',
            'first_name': 'Yasmin',
            'last_name': 'RH',
            'email': '',
            'telefone': '',
            'perfil': 'rh',
            'acesso_epi': 'on',
            'marca': 'eco_premium',
            'unidade': 'Matriz',
            'is_active': 'on',
            'password1': 'Senha-temporaria-123',
            'password2': 'Senha-temporaria-123',
        })

        self.assertRedirects(response, reverse('lista_usuarios'))
        user = User.objects.get(username='yasmin.rh')
        self.assertTrue(user.groups.filter(name='SESMET_Tecnico').exists())

        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('registrar_epi')).status_code, 200)
        self.assertEqual(self.client.get(reverse('novo_equipamento')).status_code, 200)

    def test_admin_combina_acesso_rh_e_financeiro(self):
        call_command('criar_grupos', stdout=StringIO())
        response = self.client.post(reverse('novo_usuario'), {
            'username': 'ursula.rh-financeiro',
            'first_name': 'Ursula',
            'last_name': 'RH Financeiro',
            'email': '',
            'telefone': '',
            'perfil': 'rh',
            'acesso_financeiro': 'on',
            'marca': 'eco_premium',
            'unidade': 'Matriz',
            'is_active': 'on',
            'password1': 'Senha-temporaria-123',
            'password2': 'Senha-temporaria-123',
        })

        self.assertRedirects(response, reverse('lista_usuarios'))
        user = User.objects.get(username='ursula.rh-financeiro')
        self.assertEqual(user.perfil.perfil, 'rh')
        self.assertTrue(user.groups.filter(name='Financeiro_Operador').exists())
        self.assertFalse(user.groups.filter(name='SESMET_Tecnico').exists())

        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('lista_admissoes')).status_code, 200)
        self.assertEqual(self.client.get(reverse('painel_financeiro')).status_code, 200)
        self.assertEqual(self.client.get(reverse('entrada_documento')).status_code, 200)
        self.assertRedirects(self.client.get(reverse('dashboard_sesmet')), reverse('dashboard'))
        self.assertRedirects(self.client.get(reverse('painel_compras')), reverse('dashboard'))

    def test_usuario_comum_nao_gerencia_contas(self):
        comum = User.objects.create_user('comum', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=comum, perfil='operacional')
        self.client.force_login(comum)
        self.assertEqual(self.client.get(reverse('lista_usuarios')).status_code, 403)

    def test_lista_exibe_ultima_atividade(self):
        momento = timezone.now() - timedelta(minutes=8)
        PerfilUsuario.objects.filter(usuario=self.admin).update(ultimo_acesso=momento)
        response = self.client.get(reverse('lista_usuarios'))
        self.assertContains(response, 'Última atividade')


class LastSeenMiddlewareTests(TestCase):
    def test_atualiza_ultima_atividade_do_usuario(self):
        user = User.objects.create_user('atividade', password='senha-forte-123')
        perfil = PerfilUsuario.objects.create(usuario=user, perfil='operacional')
        self.client.force_login(user)

        self.client.get(reverse('dashboard'))

        perfil.refresh_from_db()
        self.assertIsNotNone(perfil.ultimo_acesso)


class EstoqueComprasAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('estoque', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='estoque_compras')
        group, _ = Group.objects.get_or_create(name='Estoque_EPI_Compras')
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def test_abre_catalogo_e_compras(self):
        self.assertEqual(self.client.get(reverse('catalogo_equipamentos')).status_code, 200)
        self.assertEqual(self.client.get(reverse('painel_compras')).status_code, 200)

    def test_bloqueia_rh_e_area_operacional_do_sesmet(self):
        self.assertRedirects(self.client.get(reverse('lista_colaboradores')), reverse('dashboard'))
        self.assertRedirects(self.client.get(reverse('dashboard_sesmet')), reverse('catalogo_equipamentos'))

    def test_menu_mostra_somente_areas_operacionais_previstas(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Estoque de EPIs')
        self.assertContains(response, 'Compras / Almoxarifado')
        self.assertNotContains(response, 'RH / Admissional')
        self.assertNotContains(response, 'Financeiro / Fiscal')
