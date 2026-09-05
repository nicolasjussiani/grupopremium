from datetime import date
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.test import Client
from django.conf import settings
from django.urls import reverse

from administrativo.models import DemandaAdministrativa
from admissional.models import Colaborador
from core.models import AprovacaoRegistro, PerfilUsuario
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

    def test_service_worker_nao_armazena_paginas_sigilosas(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertContains(response, "event.request.mode === 'navigate'")


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
