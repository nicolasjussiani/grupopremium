from importlib import import_module
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import ControleAcessoIP, IPUsuario, LogAtividade, PerfilUsuario, PermissaoIP


@override_settings(IP_CLIENTE_VERCEL=False)
class IPAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin-ip-access', password='senha-segura-123')
        cls.user = User.objects.create_user('visitante-ip', password='senha-segura-123')
        PerfilUsuario.objects.create(usuario=cls.user, perfil='entregas_consulta')
        # Mesmo bancos que ainda têm o controle antigo ativado não bloqueiam.
        ControleAcessoIP.objects.create(pk=1, ativo=True)

    def setUp(self):
        self.admin_client = Client(REMOTE_ADDR='8.8.8.8')
        self.admin_client.force_login(self.admin)
        self.visitor = Client(REMOTE_ADDR='1.1.1.1')

    def login_visitor(self, password='senha-segura-123'):
        return self.visitor.post(reverse('login'), {
            'username': self.user.username, 'password': password,
        })

    def test_login_independe_do_status_do_ip_e_preserva_registros(self):
        for status in [None, 'pendente', 'bloqueado', 'aprovado']:
            with self.subTest(status=status):
                self.visitor.post(reverse('logout'))
                registro = None
                if status:
                    registro, _ = PermissaoIP.objects.update_or_create(
                        ip_address='1.1.1.1', defaults={'status': status},
                    )
                self.assertRedirects(self.login_visitor(), reverse('consulta_entregas'))
                self.assertTrue(IPUsuario.objects.filter(
                    usuario=self.user, ip_address='1.1.1.1', confirmado=True,
                ).exists())
                if registro:
                    registro.refresh_from_db()
                    self.assertEqual(registro.status, status)
                else:
                    self.assertFalse(PermissaoIP.objects.exists())

    def test_visitante_precisa_de_login_e_senha_valida(self):
        PermissaoIP.objects.create(ip_address='1.1.1.1', status='aprovado')
        response = self.visitor.get(reverse('consulta_entregas'))
        self.assertRedirects(response, reverse('login') + '?next=' + reverse('consulta_entregas'))
        self.assertContains(self.login_visitor(password='errada'), 'Usuário ou senha incorretos.')
        self.assertNotIn('_auth_user_id', self.visitor.session)
        self.assertFalse(IPUsuario.objects.filter(usuario=self.user).exists())

    def test_sessao_aberta_e_apis_funcionam_apos_mudar_ip(self):
        PermissaoIP.objects.create(ip_address='9.9.9.9', status='bloqueado')
        for address in ['9.9.9.9', '2001:4860:4860::8888']:
            with self.subTest(address=address):
                for route in ['controle_ips', 'lista_usuarios', 'notificacoes_json', 'status_mobile']:
                    response = self.admin_client.get(reverse(route), REMOTE_ADDR=address)
                    self.assertEqual(response.status_code, 200, route)
                self.assertTrue(IPUsuario.objects.filter(usuario=self.admin, ip_address=address).exists())

    def test_status_bloqueado_nao_interrompe_sessao_nem_post(self):
        registro = PermissaoIP.objects.create(ip_address='8.8.8.8', status='aprovado')
        response = self.admin_client.post(reverse('alterar_controle_ip'), {
            'acao': 'bloquear', 'registro_id': registro.pk,
        })
        self.assertRedirects(response, reverse('controle_ips'))
        registro.refresh_from_db()
        self.assertEqual(registro.status, 'bloqueado')
        self.assertEqual(self.admin_client.get(reverse('lista_usuarios')).status_code, 200)
        response = self.admin_client.post(reverse('alterar_controle_ip'), {
            'acao': 'aprovar', 'registro_id': registro.pk,
        })
        self.assertRedirects(response, reverse('controle_ips'))
        self.assertTrue(LogAtividade.objects.filter(acao='Controle de IP: bloquear').exists())

    def test_links_antigos_de_espera_e_login_nao_exigem_aprovacao(self):
        PermissaoIP.objects.create(ip_address='1.1.1.1', status='bloqueado')
        self.visitor.force_login(self.user)
        for route in ['aguardando_ip', 'login']:
            response = self.visitor.get(reverse(route))
            self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
            self.assertRedirects(self.visitor.get(response.url), reverse('consulta_entregas'))

    def test_permissoes_de_perfil_continuam_obrigatorias(self):
        self.login_visitor()
        for route in ['controle_ips', 'lista_usuarios', 'notificacoes_json']:
            self.assertEqual(self.visitor.get(reverse(route)).status_code, 403, route)
        self.assertEqual(self.visitor.post(reverse('alterar_controle_ip'), {
            'acao': 'desativar',
        }).status_code, 403)
        self.assertEqual(self.visitor.post(reverse('logout')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.visitor.session)

    @override_settings(IP_CLIENTE_VERCEL=True)
    def test_ip_ausente_ou_invalido_nao_impede_login_na_vercel(self):
        for value in ['', 'invalido', '8.8.8.8, 1.1.1.1']:
            with self.subTest(value=value):
                client = Client(HTTP_X_VERCEL_FORWARDED_FOR=value)
                response = client.post(reverse('login'), {
                    'username': self.user.username, 'password': 'senha-segura-123',
                })
                self.assertRedirects(response, reverse('consulta_entregas'))
        self.assertFalse(IPUsuario.objects.filter(usuario=self.user).exists())
        self.assertFalse(PermissaoIP.objects.exists())

    def test_falha_na_lista_de_ips_nao_interfere_no_login_ou_navegacao(self):
        with patch('core.models.ControleAcessoIP.objects.filter', side_effect=DatabaseError('offline')), \
                patch('core.models.PermissaoIP.objects.filter', side_effect=DatabaseError('offline')):
            self.assertEqual(self.visitor.get(reverse('login')).status_code, 200)
            self.assertRedirects(self.login_visitor(), reverse('consulta_entregas'))
            self.assertEqual(self.visitor.get(reverse('consulta_entregas')).status_code, 200)

    def test_falha_ao_registrar_historico_nao_impede_acesso(self):
        with patch('core.models.IPUsuario.objects.get_or_create', side_effect=DatabaseError('offline')), \
                self.assertLogs('core.client_ip', level='ERROR'):
            self.assertRedirects(self.login_visitor(), reverse('consulta_entregas'))
            self.assertEqual(self.visitor.get(reverse('consulta_entregas')).status_code, 200)

    def test_formulario_antigo_nao_reativa_bloqueio(self):
        response = self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'ativar'})
        self.assertRedirects(response, reverse('controle_ips'))
        self.assertFalse(ControleAcessoIP.objects.get(pk=1).ativo)
        self.assertFalse(PermissaoIP.objects.exists())
        self.assertRedirects(self.login_visitor(), reverse('consulta_entregas'))

    def test_tela_preserva_ips_e_informa_que_status_nao_bloqueia(self):
        PermissaoIP.objects.create(ip_address='1.1.1.1', status='bloqueado', solicitado_por=self.user)
        self.login_visitor()
        response = self.admin_client.get(reverse('controle_ips'))
        self.assertContains(response, 'Acesso sem aprovação por IP')
        self.assertContains(response, '1.1.1.1')
        self.assertContains(response, self.user.username)
        self.assertContains(response, 'Bloqueado')
        self.assertNotContains(response, 'value="ativar"')
        self.assertNotContains(response, 'Revogar acesso')

    def test_mutacoes_exigem_admin_post_csrf_e_ip_valido(self):
        self.visitor.force_login(self.user)
        self.assertEqual(self.visitor.post(reverse('alterar_controle_ip'), {'acao': 'ativar'}).status_code, 403)
        self.assertEqual(self.admin_client.get(reverse('alterar_controle_ip')).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True, REMOTE_ADDR='8.8.8.8')
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse('alterar_controle_ip'), {'acao': 'cadastrar', 'ip_address': '1.1.1.1'}).status_code, 403)
        for invalid in ['invalido', '8.8.8.8/24', '8.8.8.8:80', '']:
            self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'cadastrar', 'ip_address': invalid})
        self.assertFalse(PermissaoIP.objects.exists())
        self.assertEqual(self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'aprovar', 'registro_id': 'invalido'}).status_code, 403)

    def test_cadastro_normaliza_ip_e_comando_preserva_status(self):
        for address, expected in [('::ffff:1.1.1.1', '1.1.1.1'), ('2001:4860:4860::8888', '2001:4860:4860::8888')]:
            self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'cadastrar', 'ip_address': address})
            self.assertTrue(PermissaoIP.objects.filter(ip_address=expected, status='aprovado').exists())
        output = StringIO()
        call_command('autorizar_ip', '9.9.9.9', stdout=output)
        self.assertTrue(PermissaoIP.objects.filter(ip_address='9.9.9.9', status='aprovado').exists())
        self.assertIn('não interfere no acesso', output.getvalue())

    def test_migracao_desativa_configuracao_sem_apagar_dados(self):
        registro = PermissaoIP.objects.create(ip_address='1.1.1.1', status='bloqueado')
        self.login_visitor()
        history_before = list(IPUsuario.objects.values())
        migration = import_module('core.migrations.0021_desativar_bloqueio_ip')
        migration.desativar_bloqueio_ip(apps, SimpleNamespace(connection=connection))
        self.assertFalse(ControleAcessoIP.objects.get(pk=1).ativo)
        registro.refresh_from_db()
        self.assertEqual(registro.status, 'bloqueado')
        self.assertEqual(list(IPUsuario.objects.values()), history_before)
