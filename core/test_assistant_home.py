from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.assistant_navigation import processes_for_user, recommend_process
from core.models import PerfilUsuario


class AssistantHomeTests(TestCase):
    def _user(self, username, profile):
        user = User.objects.create_user(username, password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=user, perfil=profile)
        return user

    def test_dashboard_abre_com_ia_processos_e_diretorios(self):
        user = self._user('financeiro-home', 'financeiro')
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No que você está pensando?')
        self.assertContains(response, 'Financeiro &gt; Base Fiscal')
        self.assertContains(response, reverse('painel_fiscal'))
        self.assertNotContains(response, 'SESMET &gt; Registrar entrega de EPI')

    def test_pergunta_recomenda_tela_e_caminho_correto(self):
        user = self._user('rh-home', 'rh')
        self.client.force_login(user)

        response = self.client.post(reverse('dashboard'), {
            'acao': 'perguntar_ia',
            'pergunta': 'Quero cadastrar um colaborador com salário e vale transporte',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resposta da assistente')
        self.assertContains(response, 'Cadastre dados pessoais')
        self.assertContains(response, 'Admissional &gt; Colaboradores &gt; Novo colaborador')
        self.assertContains(response, reverse('novo_colaborador'))

    def test_catalogo_respeita_perfil_e_recomendacao(self):
        user = self._user('compras-home', 'compras')
        keys = {item['key'] for item in processes_for_user(user)}

        self.assertIn('compras', keys)
        self.assertNotIn('fiscal', keys)
        recommendation = recommend_process(user, 'Preciso criar uma requisição de material')
        self.assertEqual(recommendation['key'], 'compras')

    def test_link_antigo_redireciona_e_dashboard_mostra_diretorios(self):
        user = self._user('gestor-home', 'gestor')
        self.client.force_login(user)

        legacy_response = self.client.get(reverse('assistente_erp'))
        self.assertRedirects(
            legacy_response,
            f'{reverse("dashboard")}#assistente-dashboard',
            fetch_redirect_response=False,
        )

        response = self.client.post(reverse('dashboard'), {
            'acao': 'perguntar_ia',
            'pergunta': 'Onde importo a planilha fiscal?',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Caminho:')
        self.assertContains(response, 'Financeiro &gt; Base Fiscal')
