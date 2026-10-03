from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.client_ip import obter_ip_cliente
from core.models import IPUsuario, LogAtividade
from core.middleware import AuditLogMiddleware


@override_settings(IP_CLIENTE_VERCEL=True)
class ClientIPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin-ip', password='senha-forte-123')

    def test_login_registra_ip_vercel_sem_precisar_seguir_redirect(self):
        response = self.client.post(reverse('login'), {
            'username': self.user.username, 'password': 'senha-forte-123',
        }, REMOTE_ADDR='10.0.0.1', HTTP_X_VERCEL_FORWARDED_FOR='8.8.8.8')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(IPUsuario.objects.filter(usuario=self.user, ip_address='8.8.8.8', confirmado=True).exists())
        self.assertFalse(IPUsuario.objects.filter(ip_address='10.0.0.1').exists())

    def test_login_invalido_e_visitante_nao_registram_ip(self):
        self.client.post(reverse('login'), {'username': self.user.username, 'password': 'incorreta'}, HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.client.get(reverse('login'), HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.assertFalse(IPUsuario.objects.exists())

    def test_guarda_varios_ips_sem_duplicar_e_confirma_historico(self):
        anterior = timezone.now() - timedelta(days=1)
        registro = IPUsuario.objects.create(usuario=self.user, ip_address='8.8.8.8', primeiro_acesso=anterior, ultimo_acesso=anterior)
        self.client.force_login(self.user)
        for address in ['8.8.8.8', '8.8.8.8', '2001:4860:4860::8888']:
            self.client.get(reverse('lista_usuarios'), HTTP_X_FORWARDED_FOR=address)
        self.assertEqual(IPUsuario.objects.count(), 2)
        registro.refresh_from_db()
        self.assertTrue(registro.confirmado)
        self.assertEqual(registro.primeiro_acesso, anterior)
        self.assertGreater(registro.ultimo_acesso, anterior)
        response = self.client.get(reverse('lista_usuarios'))
        self.assertContains(response, '8.8.8.8')
        self.assertContains(response, '2001:4860:4860::8888')

    def test_na_vercel_nao_usa_proxy_nem_ip_invalido(self):
        factory = RequestFactory()
        for value in ['', 'invalido', '8.8.8.8, 1.1.1.1', '8.8.8.8:443']:
            request = factory.get('/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR=value)
            self.assertIsNone(obter_ip_cliente(request))
        request = factory.get('/', HTTP_X_VERCEL_FORWARDED_FOR='1.1.1.1', HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.assertEqual(obter_ip_cliente(request), '1.1.1.1')

    def test_auditoria_tambem_usa_ip_da_vercel(self):
        request = RequestFactory().post(
            '/usuarios/1/editar/', REMOTE_ADDR='10.0.0.1', HTTP_X_VERCEL_FORWARDED_FOR='8.8.8.8',
        )
        request.user = self.user
        AuditLogMiddleware(lambda request: HttpResponse()).process_response(request, HttpResponse(status=302))
        self.assertEqual(LogAtividade.objects.get().ip_address, '8.8.8.8')

    def test_acesso_recente_nao_regrava_timestamp_e_normaliza_ipv4_mapeado(self):
        self.client.force_login(self.user)
        self.client.get(reverse('lista_usuarios'), HTTP_X_FORWARDED_FOR='::ffff:8.8.8.8')
        registro = IPUsuario.objects.get()
        self.assertEqual(registro.ip_address, '8.8.8.8')
        anterior = registro.ultimo_acesso
        self.client.get(reverse('lista_usuarios'), HTTP_X_FORWARDED_FOR='8.8.8.8')
        registro.refresh_from_db()
        self.assertEqual(registro.ultimo_acesso, anterior)

    @override_settings(IP_CLIENTE_VERCEL=False)
    def test_fora_da_vercel_ignora_cabecalhos_forjados(self):
        request = RequestFactory().get('/', REMOTE_ADDR='1.1.1.1', HTTP_X_VERCEL_FORWARDED_FOR='8.8.8.8')
        self.assertEqual(obter_ip_cliente(request), '1.1.1.1')

    def test_exporta_so_publicos_confirmados_ativos_sem_repetir(self):
        now = timezone.now()
        inactive = User.objects.create_user('inativo-ip', is_active=False)
        other = User.objects.create_user('outro-ip')
        for user, address, confirmed in [
            (self.user, '8.8.8.8', True), (other, '8.8.8.8', True),
            (self.user, '10.0.0.1', True), (self.user, '1.1.1.1', False),
            (inactive, '9.9.9.9', True),
        ]:
            IPUsuario.objects.create(usuario=user, ip_address=address, confirmado=confirmed, primeiro_acesso=now, ultimo_acesso=now)
        self.client.force_login(self.user)
        response = self.client.get(reverse('lista_usuarios'), {'exportar': 'ips'})
        self.assertEqual(response.content.decode(), '8.8.8.8\n')
        self.assertIn('no-store', response['Cache-Control'])
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('lista_usuarios'), {'exportar': 'ips'}).status_code, 403)

    def test_migracao_recupera_so_ips_publicos_com_origem_nao_confirmada(self):
        for address in ['8.8.8.8', '8.8.8.8', '10.0.0.1', None]:
            LogAtividade.objects.create(usuario=self.user, acao='Histórico', ip_address=address)
        migration = import_module('core.migrations.0018_ipusuario')
        migration.importar_ips_auditoria(apps, SimpleNamespace(connection=connection))
        registro = IPUsuario.objects.get()
        self.assertEqual(registro.ip_address, '8.8.8.8')
        self.assertFalse(registro.confirmado)
