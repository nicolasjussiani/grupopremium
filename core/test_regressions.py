from datetime import date
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.http import HttpResponse
from django.test import TestCase, RequestFactory
from django.test import Client
from django.conf import settings
from django.urls import reverse

from administrativo.models import DemandaAdministrativa
from admissional.models import Colaborador
from core.middleware import AuditLogMiddleware
from core.models import AprovacaoRegistro, LogAtividade, Notificacao, PerfilUsuario
from core.validators import MAX_REQUEST_UPLOAD_SIZE, validate_document_upload
from financeiro.models import DocumentoFinanceiro, LancamentoERP
from manutencao.models import Ativo, RegistroManutencao
from sesmet.models import EquipamentoProtecao, RegistroEPI


class UploadValidationTests(TestCase):
    def test_rejeita_conteudo_incompativel_com_extensao(self):
        upload = SimpleUploadedFile(
            'documento.pdf', b'\xff\xd8\xffconteudo-jpeg', content_type='application/pdf'
        )
        with self.assertRaises(ValidationError):
            validate_document_upload(upload)

    def test_rejeita_arquivo_maior_que_limite_da_vercel(self):
        upload = SimpleUploadedFile(
            'documento.pdf',
            b'%PDF-' + b'x' * MAX_REQUEST_UPLOAD_SIZE,
            content_type='application/pdf',
        )
        with self.assertRaisesMessage(ValidationError, '4 MB'):
            validate_document_upload(upload)


class SecurityHTTPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='usuario', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='rh')

    def test_logout_exige_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)

    def test_login_rejeita_redirecionamento_externo(self):
        response = self.client.post(
            reverse('login') + '?next=https://example.invalid/roubo',
            {'username': 'usuario', 'password': 'senha-forte-123'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def test_login_csrf_funciona_no_dominio_publico_atras_da_vercel(self):
        client = Client(enforce_csrf_checks=True)
        request_options = {
            'HTTP_HOST': 'teste-eight-tau-53.vercel.app',
            'HTTP_X_FORWARDED_PROTO': 'https',
        }
        login_page = client.get(reverse('login'), **request_options)
        token = login_page.cookies['csrftoken'].value

        response = client.post(
            reverse('login'),
            {
                'username': 'usuario',
                'password': 'senha-forte-123',
                'csrfmiddlewaretoken': token,
            },
            HTTP_ORIGIN='https://teste-eight-tau-53.vercel.app',
            **request_options,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertIn('no-cache', login_page['Cache-Control'])

    def test_token_csrf_pode_ser_renovado_antes_do_face_id(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse('csrf_token_json'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['csrfToken'])
        self.assertIn('csrftoken', response.cookies)

    def test_login_com_token_expirado_recupera_em_vez_de_exibir_403(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse('login') + '?next=/mobile/',
            {'username': 'usuario', 'password': 'senha-forte-123'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('csrf=expired', response.url)
        self.assertIn('next=%2Fmobile%2F', response.url)

    def test_login_inclui_renovacao_csrf_antes_do_envio(self):
        response = self.client.get(reverse('login'))
        self.assertContains(response, reverse('csrf_token_json'))
        self.assertContains(response, "loginForm.dataset.csrfReady")

    def test_perfil_sem_acesso_nao_abre_financeiro(self):
        self.user.perfil.perfil = 'operacional'
        self.user.perfil.save(update_fields=['perfil'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('painel_financeiro'))
        self.assertRedirects(response, reverse('dashboard'))


class PageSmokeTests(TestCase):
    def test_css_publicado_permanece_sincronizado_com_a_fonte(self):
        for filename in ('main.css', 'mobile.css'):
            with self.subTest(filename=filename):
                source_css = Path(settings.BASE_DIR, 'static', 'css', filename).read_bytes()
                published_css = Path(
                    settings.BASE_DIR, 'staticfiles', 'css', filename
                ).read_bytes()
                self.assertEqual(published_css, source_css)

    def test_paginas_principais_renderizam(self):
        user = User.objects.create_superuser(
            username='admin-smoke', email='admin@example.com', password='senha-forte-123'
        )
        PerfilUsuario.objects.create(usuario=user, perfil='admin')
        self.client.force_login(user)
        rotas = (
            'dashboard', 'lista_vagas', 'banco_talentos', 'lista_admissoes',
            'lista_colaboradores', 'controle_presenca', 'periodo_experiencia',
            'lista_demandas', 'dashboard_sesmet', 'matriz_epis',
            'catalogo_equipamentos', 'painel_compras', 'lista_materiais',
            'painel_financeiro', 'painel_manutencao', 'lista_ativos',
            'lista_manutencoes', 'aprovacoes_pendentes', 'auditoria_sistema',
            'painel_sla',
        )
        for rota in rotas:
            with self.subTest(rota=rota):
                response = self.client.get(reverse(rota))
                self.assertEqual(response.status_code, 200)

    def test_layout_principal_oferece_menu_para_celular(self):
        user = User.objects.create_superuser(
            username='admin-layout-mobile',
            email='layout@example.com',
            password='senha-forte-123',
        )
        PerfilUsuario.objects.create(usuario=user, perfil='admin')
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'id="mobileMenuButton"')
        self.assertContains(response, 'aria-controls="sidebar"')
        self.assertContains(response, 'id="sidebarBackdrop"')
        self.assertContains(response, 'function setMobileMenu(open)')

    def test_secoes_de_auditoria_oferecem_layout_responsivo(self):
        user = User.objects.create_superuser(
            username='admin-auditoria-mobile',
            email='audit-mobile@example.com',
            password='senha-forte-123',
        )
        PerfilUsuario.objects.create(usuario=user, perfil='admin')
        self.client.force_login(user)

        global_response = self.client.get(reverse('auditoria_sistema'))
        sla_response = self.client.get(reverse('painel_sla'))

        self.assertContains(global_response, '@media (max-width: 768px)')
        self.assertContains(global_response, 'content: attr(data-label)')
        self.assertContains(sla_response, 'class="sla-stats"')
        self.assertContains(sla_response, '.sla-table td::before')
        financial_template = Path(
            settings.BASE_DIR, 'templates', 'financeiro', 'auditoria.html'
        ).read_text(encoding='utf-8')
        self.assertIn('financial-audit-layout', financial_template)
        self.assertIn('@media (max-width: 560px)', financial_template)

    def test_auditoria_pagina_e_filtra_sem_carregar_todo_historico(self):
        user = User.objects.create_superuser(
            username='admin-auditoria-filtros',
            email='audit-filter@example.com',
            password='senha-forte-123',
        )
        PerfilUsuario.objects.create(usuario=user, perfil='admin')
        LogAtividade.objects.bulk_create([
            LogAtividade(
                usuario=user,
                acao='Editou um registro existente' if index == 0 else 'Criou um novo registro',
                modulo='financeiro' if index == 0 else 'admissional',
                url=f'/registro/{index}/',
            )
            for index in range(35)
        ])
        self.client.force_login(user)

        primeira_pagina = self.client.get(reverse('auditoria_sistema'))
        segunda_pagina = self.client.get(reverse('auditoria_sistema'), {'page': 2})
        filtrada = self.client.get(
            reverse('auditoria_sistema'),
            {'q': '/registro/0/', 'modulo': 'financeiro', 'acao': 'editar'},
        )

        self.assertEqual(len(primeira_pagina.context['logs']), 30)
        self.assertEqual(len(segunda_pagina.context['logs']), 5)
        self.assertEqual(primeira_pagina.context['total_logs'], 35)
        self.assertEqual(filtrada.context['total_filtrados'], 1)
        self.assertContains(primeira_pagina, 'class="audit-filters"')


class AuditNotificationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.actor = User.objects.create_user('operador-auditoria')
        self.ceo = User.objects.create_superuser('ceo-auditoria', 'ceo@example.com', 'senha')
        self.admin_group = Group.objects.create(name='Admin_Global')
        self.admin = User.objects.create_user('admin-grupo-auditoria')
        self.admin.groups.add(self.admin_group)
        self.inactive_admin = User.objects.create_superuser(
            'admin-inativo-auditoria', 'inativo@example.com', 'senha', is_active=False
        )
        self.middleware = AuditLogMiddleware(lambda request: HttpResponse())

    def test_alteracao_notifica_diretoria_sem_notificar_o_autor(self):
        request = self.factory.post(
            '/admissional/colaboradores/42/editar/',
            {'nome': 'Colaborador Atualizado'},
        )
        request.user = self.actor

        self.middleware.process_response(request, HttpResponse(status=302))

        log = LogAtividade.objects.get()
        notificacoes = Notificacao.objects.order_by('destinatario__username')
        self.assertSetEqual(
            set(notificacoes.values_list('destinatario__username', flat=True)),
            {'admin-grupo-auditoria', 'ceo-auditoria'},
        )
        self.assertTrue(all(item.url_acao.endswith(f'destaque={log.pk}') for item in notificacoes))
        self.assertFalse(notificacoes.filter(destinatario=self.actor).exists())
        self.assertFalse(notificacoes.filter(destinatario=self.inactive_admin).exists())

    def test_post_de_api_nao_gera_alerta_de_alteracao(self):
        request = self.factory.post('/api/uploads/presign/', data='{}', content_type='application/json')
        request.user = self.actor

        self.middleware.process_response(request, HttpResponse(status=200))

        self.assertFalse(LogAtividade.objects.exists())
        self.assertFalse(Notificacao.objects.exists())


class MobilePwaTests(TestCase):
    def test_painel_mobile_restrito_a_diretoria(self):
        regular = User.objects.create_user('regular-mobile', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=regular, perfil='rh')
        self.client.force_login(regular)
        self.assertEqual(self.client.get(reverse('painel_mobile')).status_code, 403)

        admin = User.objects.create_superuser(
            'admin-mobile', 'admin-mobile@example.com', 'senha-forte-123'
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('painel_mobile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CENTRAL DA DIRETORIA')
        self.assertContains(response, reverse('pwa_manifest'))

    def test_manifesto_abre_o_pwa_no_painel_mobile(self):
        response = self.client.get(reverse('pwa_manifest'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/manifest+json')
        self.assertEqual(response.json()['start_url'], '/mobile/')
        self.assertEqual(response.json()['display'], 'standalone')
        icons = response.json()['icons']
        self.assertEqual(icons[0]['src'], '/static/pwa-icon-192.png')
        self.assertEqual(icons[0]['sizes'], '192x192')
        self.assertEqual(icons[1]['src'], '/static/pwa-icon-512.png')
        self.assertIn('maskable', icons[1]['purpose'])

    def test_icones_do_iphone_estao_publicados(self):
        for size in (180, 192, 512):
            with self.subTest(size=size):
                source = Path(settings.BASE_DIR, 'static', f'pwa-icon-{size}.png')
                published = Path(settings.BASE_DIR, 'staticfiles', f'pwa-icon-{size}.png')
                self.assertTrue(source.exists())
                self.assertEqual(source.read_bytes(), published.read_bytes())

    def test_service_worker_nao_armazena_paginas_sigilosas(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertContains(response, "event.request.mode === 'navigate'")
        self.assertContains(response, '/static/pwa-icon-192.png')

    def test_admin_pode_criar_notificacao_de_teste_para_si(self):
        admin = User.objects.create_superuser(
            'admin-notificacao-teste', 'notificacao@example.com', 'senha-forte-123'
        )
        self.client.force_login(admin)

        response = self.client.post(reverse('criar_notificacao_teste_mobile'))

        self.assertRedirects(response, reverse('painel_mobile') + '#notificacoes')
        notificacao = Notificacao.objects.get(destinatario=admin)
        self.assertEqual(notificacao.titulo, 'Notificação de teste')
        self.assertFalse(notificacao.lida)


class GroupCommandTests(TestCase):
    def test_admin_global_recebe_permissoes_criticas(self):
        call_command('criar_grupos', stdout=StringIO())
        group = Group.objects.get(name='Admin_Global')
        permissoes = set(group.permissions.values_list('content_type__app_label', 'codename'))
        self.assertIn(('core', 'view_logatividade'), permissoes)
        self.assertIn(('sesmet', 'change_equipamentoprotecao'), permissoes)
        self.assertIn(('manutencao', 'change_registromanutencao'), permissoes)

        sesmet_group = Group.objects.get(name='SESMET_Gestor')
        self.assertTrue(
            sesmet_group.permissions.filter(
                content_type__app_label='admissional',
                codename='change_colaborador',
            ).exists()
        )
        self.assertTrue(
            sesmet_group.permissions.filter(
                content_type__app_label='admissional',
                codename='add_colaborador',
            ).exists()
        )


class ColaboradorAccessTests(TestCase):
    def setUp(self):
        self.colaborador = Colaborador.objects.create(
            nome='Colaborador SESMET',
            cpf='111.222.333-44',
            email='colaborador@example.com',
            cargo='Operador',
            unidade='Matriz',
            data_admissao=date.today(),
        )

    def _login(self, perfil):
        user = User.objects.create_user(
            username=f'usuario-{perfil}', password='senha-forte-123'
        )
        PerfilUsuario.objects.create(usuario=user, perfil=perfil)
        self.client.force_login(user)

    def test_sesmet_pode_criar_e_editar_colaborador(self):
        self._login('sesmet')
        editar_url = reverse('editar_colaborador', args=[self.colaborador.pk])
        novo_url = reverse('novo_colaborador')

        response = self.client.get(editar_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(novo_url).status_code, 200)
        lista = self.client.get(reverse('lista_colaboradores'))
        self.assertContains(lista, editar_url)
        self.assertContains(lista, novo_url)
        self.assertNotContains(
            lista, reverse('excluir_colaborador', args=[self.colaborador.pk])
        )

    def test_gestor_sem_permissao_nao_ve_acao_de_editar(self):
        self._login('gestor')
        editar_url = reverse('editar_colaborador', args=[self.colaborador.pk])

        self.assertEqual(self.client.get(editar_url).status_code, 403)
        lista = self.client.get(reverse('lista_colaboradores'))
        self.assertNotContains(lista, editar_url)

    def test_anexos_usam_interface_compacta_sem_expor_caminho_como_texto(self):
        self.colaborador.anexo_cpf.name = 'colaboradores/docs/documento-teste.pdf'
        self.colaborador.save(update_fields=['anexo_cpf'])
        self._login('sesmet')

        response = self.client.get(
            reverse('editar_colaborador', args=[self.colaborador.pk])
        )

        self.assertContains(response, 'Documento armazenado')
        self.assertContains(response, 'Visualizar')
        self.assertContains(response, 'Substituir arquivo')
        self.assertContains(response, 'name="anexo_cpf-clear"')
        self.assertNotContains(response, 'Atualmente:')

    def test_pesquisa_colaborador_por_nome_e_codigo(self):
        outro = Colaborador.objects.create(
            nome='Maria da Silva',
            cpf='555.666.777-88',
            email='maria@example.com',
            cargo='Analista',
            unidade='Filial',
            data_admissao=date.today(),
        )
        self._login('sesmet')
        lista_url = reverse('lista_colaboradores')

        por_nome = self.client.get(lista_url, {'q': 'Colaborador SESMET'})
        self.assertContains(por_nome, self.colaborador.nome)
        self.assertNotContains(por_nome, outro.nome)
        self.assertEqual(por_nome.context['total'], 1)

        por_codigo = self.client.get(lista_url, {'q': f'{self.colaborador.pk:04d}'})
        self.assertContains(por_codigo, self.colaborador.nome)
        self.assertNotContains(por_codigo, outro.nome)


class WorkflowIntegrityTests(TestCase):
    def _user(self, username, perfil, group=None):
        user = User.objects.create_user(username=username, password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=user, perfil=perfil)
        if group:
            user.groups.add(Group.objects.create(name=group))
        return user

    def test_rejeicao_de_manutencao_libera_ativo(self):
        solicitante = self._user('solicitante-manut', 'sesmet')
        aprovador = self._user('diretor', 'gestor', 'Diretoria_Final')
        ativo = Ativo.objects.create(
            numero_patrimonio='PAT-001', nome='Empilhadeira', unidade_atual='Matriz',
            status='manutencao',
        )
        registro = RegistroManutencao.objects.create(
            ativo=ativo, unidade_origem='Matriz', motivo='Reparo',
            data_inicio=date.today(), status='aguardando_aprovacao',
            registrado_por=solicitante,
        )
        aprovacao = AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(registro),
            object_id=registro.pk,
            modulo='manutencao',
            nivel=2,
            titulo='Reparo da empilhadeira',
            solicitado_por=solicitante,
        )
        self.client.force_login(aprovador)
        response = self.client.post(
            reverse('rejeitar_registro', args=[aprovacao.pk]),
            {'motivo_rejeicao': 'Orcamento incompleto'},
        )
        self.assertEqual(response.status_code, 302)
        registro.refresh_from_db()
        ativo.refresh_from_db()
        self.assertEqual(registro.status, 'cancelada')
        self.assertEqual(ativo.status, 'ativo')

    def test_rejeicao_de_lancamento_reabre_documento(self):
        aprovador = self._user('financeiro-aprovador', 'financeiro', 'Financeiro_Aprovador')
        documento = DocumentoFinanceiro.objects.create(
            tipo='nota_fiscal', numero_documento='NF-1', descricao='Teste', valor='10.00',
            centro_custo='ADM', unidade='Matriz', cnpj_emitente='00000000000100',
            razao_social_emitente='Fornecedor', data_emissao=date.today(), status='lancado',
        )
        lancamento = LancamentoERP.objects.create(
            documento=documento, descricao='Teste', tipo='debito', valor='10.00',
            centro_custo='ADM', competencia=date.today().replace(day=1), status='em_validacao',
        )
        self.client.force_login(aprovador)
        response = self.client.post(
            reverse('validar_lancamento', args=[lancamento.pk]),
            {'acao': 'rejeitar', 'motivo_rejeicao': 'Centro de custo incorreto'},
        )
        self.assertEqual(response.status_code, 302)
        lancamento.refresh_from_db()
        documento.refresh_from_db()
        self.assertEqual(lancamento.status, 'rejeitado')
        self.assertEqual(documento.status, 'aprovado_lancamento')

    def test_movimentacao_epi_preserva_estoque(self):
        colaborador = Colaborador.objects.create(
            nome='Pessoa Teste', cpf='000.000.000-00', email='pessoa@example.com',
            cargo='Operador', unidade='Matriz', data_admissao=date.today(),
        )
        equipamento = EquipamentoProtecao.objects.create(
            nome='Capacete', dias_durabilidade=30, estoque_atual=5,
        )
        registro = RegistroEPI.objects.create(
            colaborador=colaborador, equipamento=equipamento,
            tipo_movimentacao='retirada', quantidade=3, data_movimentacao=date.today(),
        )
        equipamento.refresh_from_db()
        self.assertEqual(equipamento.estoque_atual, 2)
        registro.quantidade = 1
        with self.assertRaises(ValidationError):
            registro.save()

    def test_status_administrativo_invalido_nao_e_salvo(self):
        gestor = self._user('gestor', 'gestor')
        demanda = DemandaAdministrativa.objects.create(
            tipo='contratos', titulo='Contrato', descricao='Revisar contrato',
            requisitante='Area', prioridade='media', status='em_triagem',
        )
        self.client.force_login(gestor)
        response = self.client.post(
            reverse('atualizar_status_demanda', args=[demanda.pk]),
            {'status': 'status-inexistente'},
        )
        self.assertEqual(response.status_code, 302)
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, 'em_triagem')
