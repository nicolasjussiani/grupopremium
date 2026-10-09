from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import DatabaseError
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

    def setUp(self):
        self.admin_client = Client(REMOTE_ADDR='8.8.8.8')
        self.admin_client.force_login(self.admin)
        self.visitor = Client(REMOTE_ADDR='1.1.1.1')

    def activate(self):
        return self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'ativar'})

    def login_visitor(self, password='senha-segura-123'):
        return self.visitor.post(reverse('login'), {'username': self.user.username, 'password': password})

    def decide(self, acao, address='1.1.1.1'):
        registro = PermissaoIP.objects.get(ip_address=address)
        return self.admin_client.post(reverse('alterar_controle_ip'), {'acao': acao, 'registro_id': registro.pk})

    def test_ativacao_explicita_aprova_apenas_ip_atual_e_audita(self):
        self.assertFalse(ControleAcessoIP.objects.exists())
        self.assertEqual(self.admin_client.get(reverse('controle_ips')).status_code, 200)
        self.assertEqual(self.activate().status_code, 302)
        self.assertTrue(ControleAcessoIP.objects.get(pk=1).ativo)
        self.assertEqual(list(PermissaoIP.objects.values_list('ip_address', 'status')), [('8.8.8.8', 'aprovado')])
        self.assertTrue(LogAtividade.objects.filter(acao='Controle de IP: ativar', detalhes='IP: 8.8.8.8').exists())

    def test_visitante_bloqueado_mas_login_acessivel_sem_criar_solicitacao(self):
        self.activate()
        for path in ['/', '/usuarios/', '/admin/', '/api/notificacoes/', '/media/segredo.pdf', '/static/css/main.css', '/login/falso/']:
            response = self.visitor.get(path)
            self.assertEqual(response.status_code, 403, path)
            self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.visitor.get(reverse('login')).status_code, 200)
        self.assertEqual(self.visitor.get(reverse('csrf_token_json')).status_code, 200)
        self.assertEqual(self.login_visitor(password='errada').status_code, 200)
        self.assertFalse(PermissaoIP.objects.filter(ip_address='1.1.1.1').exists())

    def test_fluxo_login_espera_aprovacao_e_perfil_entregas(self):
        self.activate()
        response = self.login_visitor()
        self.assertRedirects(response, reverse('aguardando_ip'))
        registro = PermissaoIP.objects.get(ip_address='1.1.1.1')
        self.assertEqual(registro.status, 'pendente')
        self.assertEqual(registro.solicitado_por, self.user)
        self.assertTrue(IPUsuario.objects.filter(usuario=self.user, ip_address='1.1.1.1').exists())
        waiting = self.visitor.get(reverse('aguardando_ip'))
        self.assertContains(waiting, 'Aguardando aprovação')
        self.assertContains(waiting, '1.1.1.1')
        self.assertNotContains(waiting, 'sidebar')
        self.assertContains(self.admin_client.get(reverse('controle_ips')), self.user.username)
        self.decide('aprovar')
        self.assertRedirects(self.visitor.get(reverse('aguardando_ip')), reverse('dashboard'), fetch_redirect_response=False)
        self.assertEqual(self.visitor.get(reverse('consulta_entregas')).status_code, 200)
        self.assertEqual(self.visitor.get(reverse('controle_ips')).status_code, 403)

    def test_sessao_pendente_nao_acessa_api_post_admin_ou_arquivo(self):
        self.activate()
        self.login_visitor()
        for path in ['/admin/', '/usuarios/', '/financeiro/', '/media/segredo.pdf', '/static/css/main.css']:
            self.assertRedirects(self.visitor.get(path), reverse('aguardando_ip'), fetch_redirect_response=False)
        for path in ['/api/notificacoes/', '/mobile/status/']:
            self.assertEqual(self.visitor.get(path).status_code, 403)
        self.assertEqual(self.visitor.post(reverse('alterar_controle_ip'), {'acao': 'desativar'}).status_code, 403)
        self.assertTrue(ControleAcessoIP.objects.get(pk=1).ativo)
        self.assertEqual(self.visitor.post(reverse('logout')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.visitor.session)

    def test_recusa_nao_reabre_e_revogacao_bloqueia_sessao_aberta(self):
        self.activate()
        self.login_visitor()
        self.decide('bloquear')
        self.assertContains(self.visitor.get(reverse('aguardando_ip')), 'Acesso não autorizado')
        self.visitor.post(reverse('logout'))
        self.login_visitor()
        self.assertEqual(PermissaoIP.objects.get(ip_address='1.1.1.1').status, 'bloqueado')
        self.decide('aprovar')
        self.assertEqual(self.visitor.get(reverse('consulta_entregas')).status_code, 200)
        self.decide('bloquear')
        self.assertRedirects(self.visitor.get(reverse('consulta_entregas')), reverse('aguardando_ip'), fetch_redirect_response=False)

    def test_mudar_ip_revalida_sessao_inclusive_administrador(self):
        self.activate()
        response = self.admin_client.get(reverse('controle_ips'), REMOTE_ADDR='9.9.9.9')
        self.assertRedirects(response, reverse('aguardando_ip'), fetch_redirect_response=False)
        self.assertEqual(PermissaoIP.objects.get(ip_address='9.9.9.9').status, 'pendente')

    def test_aprovacao_global_nao_substitui_senha_nem_permissoes(self):
        self.activate()
        self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'cadastrar', 'ip_address': '1.1.1.1'})
        self.assertEqual(self.visitor.get(reverse('consulta_entregas')).status_code, 302)
        self.assertRedirects(self.login_visitor(), reverse('consulta_entregas'))
        another = User.objects.create_user('outra-conta-ip', password='senha-segura-123')
        self.visitor.post(reverse('logout'))
        response = self.visitor.post(reverse('login'), {'username': another.username, 'password': 'senha-segura-123'})
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.assertEqual(self.visitor.get(reverse('controle_ips')).status_code, 403)

    def test_normaliza_ipv6_e_nao_confia_em_cabecalho_fora_vercel(self):
        self.activate()
        self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'cadastrar', 'ip_address': '::ffff:1.1.1.1'})
        self.assertTrue(PermissaoIP.objects.filter(ip_address='1.1.1.1', status='aprovado').exists())
        response = self.visitor.get('/', REMOTE_ADDR='9.9.9.9', HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.assertEqual(response.status_code, 403)
        self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'cadastrar', 'ip_address': '2001:4860:4860::8888'})
        self.assertTrue(PermissaoIP.objects.filter(ip_address='2001:4860:4860::8888', status='aprovado').exists())

    @override_settings(IP_CLIENTE_VERCEL=True)
    def test_vercel_ip_ausente_nao_libera_nem_cria_solicitacao(self):
        ControleAcessoIP.objects.create(pk=1, ativo=True)
        PermissaoIP.objects.create(ip_address='1.1.1.1', status='aprovado')
        self.assertEqual(self.visitor.get('/').status_code, 403)
        self.login_visitor()
        self.assertContains(self.visitor.get(reverse('aguardando_ip')), 'Não foi possível identificar seu IP')
        self.assertEqual(self.visitor.get(reverse('consulta_entregas'), HTTP_X_VERCEL_FORWARDED_FOR='1.1.1.1').status_code, 200)

    def test_falha_banco_falha_fechada(self):
        with patch('core.ip_access.controle_ip_ativo', side_effect=DatabaseError('offline')):
            response = self.visitor.get('/')
        self.assertEqual(response.status_code, 503)
        self.assertIn('no-store', response['Cache-Control'])

    def test_admin_nao_revoga_ip_proprio_e_pode_desativar(self):
        self.activate()
        self.decide('bloquear', '8.8.8.8')
        self.assertEqual(PermissaoIP.objects.get(ip_address='8.8.8.8').status, 'aprovado')
        self.login_visitor()
        self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'desativar'})
        self.assertEqual(self.visitor.get(reverse('consulta_entregas')).status_code, 200)

    def test_mutacoes_exigem_admin_post_csrf_e_ip_valido(self):
        self.visitor.force_login(self.user)
        self.assertEqual(self.visitor.post(reverse('alterar_controle_ip'), {'acao': 'ativar'}).status_code, 403)
        self.assertEqual(self.admin_client.get(reverse('alterar_controle_ip')).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True, REMOTE_ADDR='8.8.8.8')
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse('alterar_controle_ip'), {'acao': 'ativar'}).status_code, 403)
        for invalid in ['invalido', '8.8.8.8/24', '8.8.8.8:80', '']:
            self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'cadastrar', 'ip_address': invalid})
        self.assertFalse(PermissaoIP.objects.exists())
        self.assertEqual(self.admin_client.post(reverse('alterar_controle_ip'), {'acao': 'aprovar', 'registro_id': 'invalido'}).status_code, 403)

    def test_comando_recupera_rede_sem_desativar_bloqueio(self):
        self.activate()
        call_command('autorizar_ip', '9.9.9.9', stdout=StringIO())
        self.assertEqual(self.admin_client.get(reverse('controle_ips'), REMOTE_ADDR='9.9.9.9').status_code, 200)
        self.assertTrue(ControleAcessoIP.objects.get(pk=1).ativo)
