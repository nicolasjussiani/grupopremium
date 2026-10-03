from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from core.models import PerfilUsuario


class MaintenanceAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('estoque-teste')
        PerfilUsuario.objects.create(usuario=self.user, perfil='estoque_compras')
        self.user.groups.add(Group.objects.get_or_create(name='Estoque_EPI_Compras')[0])
        self.client.force_login(self.user)

    def grant(self, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='manutencao', codename__in=codes,
        ))

    def test_stock_profile_without_grant_stays_blocked(self):
        response = self.client.get(reverse('painel_manutencao'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_explicit_grant_opens_module_menu_and_forms(self):
        self.grant('view_ativo', 'add_ativo', 'view_registromanutencao', 'add_registromanutencao')
        for route in ('painel_manutencao', 'lista_ativos', 'novo_ativo', 'lista_manutencoes', 'nova_manutencao'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'href="' + reverse('painel_manutencao') + '"')
        response = self.client.get(reverse('lista_colaboradores'))
        self.assertEqual(response.status_code, 302)

    def test_read_permission_does_not_allow_creation(self):
        self.grant('view_ativo')
        self.assertEqual(self.client.get(reverse('lista_ativos')).status_code, 200)
        self.assertEqual(self.client.get(reverse('novo_ativo')).status_code, 403)
