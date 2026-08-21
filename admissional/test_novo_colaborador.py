"""
Testes para a area de Novos Colaboradores - diagnostico do erro 505
ERP Grupo PremiumBR

Execucao:
    python manage.py test admissional.test_novo_colaborador -v 2
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse, resolve
from admissional.models import Colaborador
from admissional.forms import ColaboradorForm
import datetime


# ─── Fixtures / helpers ───────────────────────────────────────────────────────

def _make_user(username='testuser', password='testpass123'):
    """Cria e retorna um usuario de teste."""
    return User.objects.create_user(username=username, password=password)


def _colaborador_data(**overrides):
    """Retorna dados minimos validos para criar um Colaborador."""
    base = {
        'nome': 'Joao da Silva',
        'cpf': '111.222.333-44',
        'rg': '',
        'data_nascimento': '',
        'email': 'joao@email.com',
        'telefone': '11999998888',
        'endereco': '',
        'tipo_contrato': 'clt',
        'cargo': 'Motorista',
        'setor': '',
        'unidade': 'SP-01',
        'marca': 'eco_premium',
        'data_admissao': datetime.date.today().isoformat(),
        'status': 'ativo',
        'pis_pasep': '',
        'ctps': '',
        'salario': '',
    }
    base.update(overrides)
    return base


# ─── 1. Testes de URL e Roteamento ───────────────────────────────────────────

class TestNovoColaboradorURL(TestCase):
    """Verifica se as URLs da area de colaboradores estao configuradas."""

    def test_url_novo_colaborador_resolve(self):
        """URL novo_colaborador deve resolver para a view correta."""
        url = reverse('novo_colaborador')
        match = resolve(url)
        self.assertEqual(match.func.__name__, 'novo_colaborador')

    def test_url_lista_colaboradores_resolve(self):
        """URL lista_colaboradores deve resolver corretamente."""
        url = reverse('lista_colaboradores')
        match = resolve(url)
        self.assertEqual(match.func.__name__, 'lista_colaboradores')

    def test_url_editar_colaborador_resolve(self):
        """URL editar_colaborador deve resolver com pk."""
        url = reverse('editar_colaborador', args=[1])
        match = resolve(url)
        self.assertEqual(match.func.__name__, 'editar_colaborador')

    def test_url_excluir_colaborador_resolve(self):
        """URL excluir_colaborador deve resolver com pk."""
        url = reverse('excluir_colaborador', args=[1])
        match = resolve(url)
        self.assertEqual(match.func.__name__, 'excluir_colaborador')


# ─── 2. Testes de Autenticacao ────────────────────────────────────────────────

class TestNovoColaboradorAutenticacao(TestCase):
    """Verifica comportamento com e sem autenticacao."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('novo_colaborador')

    def test_redireciona_usuario_nao_autenticado_GET(self):
        """GET sem login deve redirecionar para /login/."""
        response = self.client.get(self.url)
        self.assertIn(response.status_code, [302, 301])
        self.assertIn('/login/', response['Location'])

    def test_redireciona_usuario_nao_autenticado_POST(self):
        """POST sem login deve redirecionar para /login/."""
        response = self.client.post(self.url, data=_colaborador_data())
        self.assertIn(response.status_code, [302, 301])


# ─── 3. Testes de Resposta HTTP — foco no erro 505 ───────────────────────────

class TestNovoColaboradorHTTP(TestCase):
    """
    Testes que investigam o erro 505 (HTTP Version Not Supported)
    e outros erros 5xx na view novo_colaborador.
    """

    def setUp(self):
        self.user = _make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('novo_colaborador')

    # GET

    def test_GET_retorna_200(self):
        """GET autenticado deve retornar 200 OK, sem erro 5xx."""
        response = self.client.get(self.url)
        self.assertEqual(
            response.status_code, 200,
            'ERRO %d: GET /colaboradores/novo/ falhou. Esperado 200. Possivel 505 ou 500.' % response.status_code
        )

    def test_GET_usa_template_correto(self):
        """GET deve renderizar form_colaborador.html."""
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'admissional/form_colaborador.html')

    def test_GET_contem_formulario_no_contexto(self):
        """Contexto do GET deve conter ColaboradorForm."""
        response = self.client.get(self.url)
        self.assertIn('form', response.context)
        self.assertIsInstance(response.context['form'], ColaboradorForm)

    def test_GET_contem_acao_novo(self):
        """Contexto deve conter 'acao' = 'Novo'."""
        response = self.client.get(self.url)
        self.assertEqual(response.context.get('acao'), 'Novo')

    # POST valido

    def test_POST_valido_cria_colaborador(self):
        """POST com dados validos deve criar colaborador e redirecionar."""
        response = self.client.post(self.url, data=_colaborador_data())
        self.assertEqual(
            response.status_code, 302,
            'ERRO %d: POST valido deveria redirecionar (302).' % response.status_code
        )
        self.assertTrue(Colaborador.objects.filter(cpf='111.222.333-44').exists())

    def test_POST_valido_redireciona_para_lista(self):
        """Apos criar, deve redirecionar para lista_colaboradores."""
        response = self.client.post(self.url, data=_colaborador_data())
        self.assertRedirects(response, reverse('lista_colaboradores'))

    def test_POST_com_arquivo_multipart(self):
        """POST multipart/form-data com upload nao deve retornar 505."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile('cpf.pdf', b'%PDF-fake', content_type='application/pdf')
        data = _colaborador_data(cpf='555.666.777-88')
        data['anexo_cpf'] = fake_file
        response = self.client.post(self.url, data=data, format='multipart')
        self.assertIn(
            response.status_code, [200, 302],
            'ERRO %d: Upload causou erro. Codigo 505 indica problema com HTTP version.' % response.status_code
        )

    # POST invalido

    def test_POST_sem_dados_obrigatorios_retorna_200(self):
        """POST vazio deve retornar 200 com erros de form, nao 5xx."""
        response = self.client.post(self.url, data={})
        self.assertEqual(
            response.status_code, 200,
            'ERRO %d: POST vazio nao deve retornar 5xx.' % response.status_code
        )

    def test_POST_sem_nome_exibe_erro_validacao(self):
        """POST sem nome deve exibir erro no campo nome."""
        data = _colaborador_data(nome='')
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('nome'))

    def test_POST_sem_cpf_exibe_erro_validacao(self):
        """POST sem CPF deve exibir erro no campo cpf."""
        data = _colaborador_data(cpf='')
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('cpf'))

    def test_POST_sem_data_admissao_exibe_erro_validacao(self):
        """POST sem data_admissao deve exibir erro no campo."""
        data = _colaborador_data(data_admissao='')
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('data_admissao'))

    def test_POST_cpf_duplicado_nao_causa_5xx(self):
        """CPF duplicado deve retornar 200 com erro de form, nao 5xx."""
        Colaborador.objects.create(
            nome='Primeiro Colaborador',
            cpf='999.888.777-66',
            email='primeiro@email.com',
            telefone='11000000000',
            cargo='Auxiliar',
            unidade='RJ-01',
            data_admissao=datetime.date.today(),
            status='ativo',
        )
        data = _colaborador_data(cpf='999.888.777-66', nome='Segundo Colaborador')
        response = self.client.post(self.url, data=data)
        self.assertEqual(
            response.status_code, 200,
            'ERRO %d: CPF duplicado nao deve causar 5xx.' % response.status_code
        )
        self.assertTrue(response.context['form'].errors)


# ─── 4. Testes de Modelo ─────────────────────────────────────────────────────

class TestColaboradorModel(TestCase):
    """Valida a integridade do modelo Colaborador."""

    def test_criacao_minima_valida(self):
        """Deve ser possivel criar Colaborador com dados minimos."""
        c = Colaborador.objects.create(
            nome='Maria Oliveira',
            cpf='123.456.789-00',
            email='maria@email.com',
            telefone='11900000001',
            cargo='Analista',
            unidade='MG-01',
            data_admissao=datetime.date.today(),
            status='ativo',
        )
        self.assertIsNotNone(c.pk)

    def test_cpf_deve_ser_unico(self):
        """Dois colaboradores nao podem ter o mesmo CPF."""
        Colaborador.objects.create(
            nome='Carlos Santos',
            cpf='321.654.987-00',
            email='carlos@email.com',
            telefone='11900000002',
            cargo='Motorista',
            unidade='BA-01',
            data_admissao=datetime.date.today(),
            status='ativo',
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Colaborador.objects.create(
                nome='Carlos Duplicado',
                cpf='321.654.987-00',
                email='carlos2@email.com',
                telefone='11900000003',
                cargo='Motorista',
                unidade='BA-01',
                data_admissao=datetime.date.today(),
                status='ativo',
            )

    def test_status_padrao_e_ativo(self):
        """Status padrao de novo Colaborador deve ser 'ativo'."""
        c = Colaborador(
            nome='Teste Status',
            cpf='000.000.000-01',
            email='t@t.com',
            telefone='00',
            cargo='Cargo',
            unidade='XX',
            data_admissao=datetime.date.today(),
        )
        self.assertEqual(c.status, 'ativo')


# ─── 5. Testes de Formulario ─────────────────────────────────────────────────

class TestColaboradorForm(TestCase):
    """Valida o ColaboradorForm diretamente."""

    def test_form_valido_com_dados_minimos(self):
        """Form deve ser valido com dados minimos corretos."""
        form = ColaboradorForm(data=_colaborador_data())
        self.assertTrue(form.is_valid(), 'Form invalido: %s' % form.errors)

    def test_form_invalido_sem_nome(self):
        form = ColaboradorForm(data=_colaborador_data(nome=''))
        self.assertFalse(form.is_valid())
        self.assertIn('nome', form.errors)

    def test_form_invalido_sem_cpf(self):
        form = ColaboradorForm(data=_colaborador_data(cpf=''))
        self.assertFalse(form.is_valid())
        self.assertIn('cpf', form.errors)

    def test_form_invalido_sem_email(self):
        form = ColaboradorForm(data=_colaborador_data(email=''))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_form_invalido_email_mal_formatado(self):
        form = ColaboradorForm(data=_colaborador_data(email='isso-nao-e-email'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_form_invalido_sem_cargo(self):
        form = ColaboradorForm(data=_colaborador_data(cargo=''))
        self.assertFalse(form.is_valid())
        self.assertIn('cargo', form.errors)

    def test_form_invalido_sem_unidade(self):
        form = ColaboradorForm(data=_colaborador_data(unidade=''))
        self.assertFalse(form.is_valid())
        self.assertIn('unidade', form.errors)

    def test_form_invalido_sem_data_admissao(self):
        form = ColaboradorForm(data=_colaborador_data(data_admissao=''))
        self.assertFalse(form.is_valid())
        self.assertIn('data_admissao', form.errors)

    def test_form_widgets_tem_classe_form_control(self):
        """Todos os campos devem ter a classe CSS form-control."""
        form = ColaboradorForm()
        for name, field in form.fields.items():
            widget_class = field.widget.attrs.get('class', '')
            self.assertIn('form-control', widget_class)


# ─── 6. Diagnostico especifico do erro 505 ───────────────────────────────────

class TestDiagnostico505(TestCase):
    """
    Suite dedicada a simular cenarios que podem gerar o erro 505
    (HTTP Version Not Supported) ou outros erros 5xx na view novo_colaborador.
    """

    def setUp(self):
        self.user = _make_user(username='diag_user')
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('novo_colaborador')

    def test_GET_nao_retorna_505(self):
        """
        GET nao deve retornar 505.
        505 = HTTP Version Not Supported, geralmente causado por
        middleware ou configuracao WSGI/ASGI incorreta.
        """
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 505,
            'ERRO 505 no GET! Verificar middleware e configuracao WSGI/ASGI.')
        self.assertLess(response.status_code, 500,
            'ERRO %d: GET retornou erro de servidor. Verificar views.py e imports.' % response.status_code)

    def test_POST_nao_retorna_505(self):
        """
        POST nao deve retornar 505.
        Se retornar 505, verificar middleware, WSGI/ASGI e server version.
        """
        response = self.client.post(self.url, data=_colaborador_data())
        self.assertNotEqual(response.status_code, 505,
            'ERRO 505 no POST! Verificar middleware e WSGI/ASGI.')
        self.assertIn(response.status_code, [200, 302],
            'ERRO %d: POST retornou codigo inesperado.' % response.status_code)

    def test_view_importa_sem_erros(self):
        """
        Imports da view nao devem causar excecao.
        Imports quebrados causam 500/505 em todas as requisicoes.
        """
        try:
            from admissional import views
            self.assertTrue(hasattr(views, 'novo_colaborador'),
                'Funcao novo_colaborador nao encontrada em admissional.views.')
            self.assertTrue(hasattr(views, 'lista_colaboradores'),
                'Funcao lista_colaboradores nao encontrada em admissional.views.')
            self.assertTrue(hasattr(views, 'editar_colaborador'),
                'Funcao editar_colaborador nao encontrada em admissional.views.')
            self.assertTrue(hasattr(views, 'excluir_colaborador'),
                'Funcao excluir_colaborador nao encontrada em admissional.views.')
        except ImportError as e:
            self.fail('Erro de import em admissional.views: %s' % e)

    def test_model_importa_sem_erros(self):
        """Model Colaborador deve importar sem erros."""
        try:
            from admissional.models import Colaborador
            self.assertTrue(True)
        except ImportError as e:
            self.fail('Erro de import em admissional.models: %s' % e)

    def test_form_importa_sem_erros(self):
        """ColaboradorForm deve importar sem erros."""
        try:
            from admissional.forms import ColaboradorForm
            self.assertTrue(True)
        except ImportError as e:
            self.fail('Erro de import em admissional.forms: %s' % e)

    def test_headers_normais_nao_causam_505(self):
        """
        Requisicao com headers HTTP normais nao deve causar 505.
        505 pode ser causado por headers mal formados.
        """
        response = self.client.get(
            self.url,
            HTTP_ACCEPT='text/html,application/xhtml+xml',
            HTTP_ACCEPT_LANGUAGE='pt-BR,pt;q=0.9',
            HTTP_ACCEPT_ENCODING='gzip, deflate',
        )
        self.assertNotEqual(response.status_code, 505,
            'Headers normais causaram erro 505!')

    def test_lista_colaboradores_nao_retorna_5xx(self):
        """lista_colaboradores nao deve retornar 5xx."""
        response = self.client.get(reverse('lista_colaboradores'))
        self.assertLess(response.status_code, 500,
            'ERRO %d: lista_colaboradores retornou erro de servidor.' % response.status_code)

    def test_novo_colaborador_GET_nao_retorna_5xx(self):
        """novo_colaborador GET nao deve retornar 5xx."""
        response = self.client.get(self.url)
        self.assertLess(response.status_code, 500,
            'ERRO %d: novo_colaborador GET retornou erro de servidor.' % response.status_code)

    def test_post_multipart_nao_gera_505(self):
        """
        POST multipart nao deve gerar 505.
        Cenario comum que pode acionar o erro quando enctype
        ou configuracao de upload esta incorreta.
        """
        data = _colaborador_data(cpf='777.888.999-11')
        response = self.client.post(
            self.url,
            data=data,
            content_type='multipart/form-data'
        )
        self.assertNotEqual(response.status_code, 505,
            'POST multipart/form-data causou erro 505! '
            'Verificar enctype do formulario e configuracao de upload.')
