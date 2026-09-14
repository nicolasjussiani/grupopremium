from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.models import PerfilUsuario
from core.views import server_error_view


class ErrorPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('usuario-sem-acesso', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='operacional')

    @override_settings(DEBUG=False)
    def test_pagina_inexistente_e_exibida_em_portugues(self):
        response = self.client.get('/pagina-que-nao-existe/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Página não encontrada', status_code=404)
        self.assertContains(response, 'Voltar ao painel', status_code=404)

    @override_settings(DEBUG=False)
    def test_acesso_negado_exibe_orientacao_sem_traceback(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('lista_usuarios'))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Acesso não autorizado', status_code=403)
        self.assertNotContains(response, 'Traceback', status_code=403)

    def test_erro_interno_tem_resposta_segura_em_portugues(self):
        response = server_error_view(RequestFactory().get('/falha/'))
        self.assertEqual(response.status_code, 500)
        self.assertIn('Não foi possível concluir', response.content.decode())


class AccessibilitySmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin-acessibilidade', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='admin')
        self.client.force_login(self.user)

    def test_layout_tem_atalho_e_conteudo_principal(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'href="#conteudo-principal"')
        self.assertContains(response, 'id="conteudo-principal"')
        self.assertContains(response, 'aria-label="Sair do sistema"')

    def test_filtros_principais_possuem_rotulos(self):
        for route_name, label in (
            ('lista_vagas', 'Filtrar vagas por status'),
            ('lista_admissoes', 'Filtrar admissões por status'),
            ('aprovacoes_pendentes', 'Filtrar aprovações por módulo'),
        ):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertContains(response, label)
