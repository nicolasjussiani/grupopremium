from datetime import date, timedelta

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import URLResolver, get_resolver, reverse

from administrativo.models import DemandaAdministrativa
from admissional.models import Admissao, Colaborador, DocumentoAdmissional
from compras.models import Material, PedidoCompra, SolicitacaoMaterial
from core.models import AprovacaoRegistro, Notificacao, PerfilUsuario
from financeiro.models import DocumentoFinanceiro, LancamentoERP
from manutencao.models import Ativo, RegistroManutencao
from recrutamento.models import Candidato, Talento, Vaga
from sesmet.models import EquipamentoProtecao, RegistroEPI


class FullSiteRouteTests(TestCase):
    """Render every application route with representative persisted data."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username='admin-full-site',
            email='admin-full-site@example.com',
            password='senha-forte-123',
        )
        PerfilUsuario.objects.create(usuario=cls.user, perfil='admin')

        cls.vaga = Vaga.objects.create(
            nome_vaga='Operador',
            quantidade_colaboradores=1,
            cidade='Sao Paulo',
            unidade='Matriz',
            perfil_desejado='Perfil de teste',
            atividades='Atividades de teste',
            horario_trabalho='08:00-17:00',
            tipo_contratacao='clt',
            valor_salario='2500.00',
            previsao_inicio=date.today() + timedelta(days=10),
            motivo_solicitacao='Teste integral do site',
            gestor_responsavel='Gestor Teste',
            gestor_usuario=cls.user,
            status='em_selecao',
        )
        cls.candidato = Candidato.objects.create(
            vaga=cls.vaga,
            nome='Candidato Teste',
            email='candidato@example.com',
            telefone='11999999999',
            cidade='Sao Paulo',
            cpf_cnpj='222.333.444-55',
            arquivo_pdf=b'%PDF-1.4 teste',
        )
        cls.talento = Talento.objects.create(
            nome='Talento Teste',
            email='talento@example.com',
            telefone='11988888888',
            cidade='Sao Paulo',
            cpf_cnpj='333.444.555-66',
            arquivo_pdf=b'%PDF-1.4 teste',
            ultima_vaga=cls.vaga,
        )
        cls.colaborador = Colaborador.objects.create(
            nome='Colaborador Teste Integral',
            cpf='444.555.666-77',
            email='colaborador-integral@example.com',
            cargo='Operador',
            unidade='Matriz',
            data_admissao=date.today(),
        )
        cls.admissao = Admissao.objects.create(
            candidato_nome='Pessoa em Admissao',
            candidato_email='admissao@example.com',
            candidato_telefone='11977777777',
            vaga_nome='Operador',
            unidade_destino='Matriz',
            colaborador=cls.colaborador,
            responsavel_rh=cls.user,
        )
        cls.documento_admissional = DocumentoAdmissional.objects.create(
            admissao=cls.admissao,
            tipo='rg',
            status='aprovado',
            arquivo=b'documento de teste',
            arquivo_nome='rg-teste.pdf',
            arquivo_mimetype='application/pdf',
        )
        cls.demanda = DemandaAdministrativa.objects.create(
            tipo='contratos',
            titulo='Demanda de teste',
            descricao='Teste integral',
            requisitante='Usuario Teste',
            requisitante_usuario=cls.user,
        )
        cls.material = Material.objects.create(
            codigo='MAT-FULL',
            nome='Material de teste',
            quantidade_estoque=10,
            estoque_minimo=2,
            preco_unitario='15.00',
        )
        cls.solicitacao = SolicitacaoMaterial.objects.create(
            material=cls.material,
            quantidade_solicitada=2,
            solicitante='Usuario Teste',
            solicitante_usuario=cls.user,
            unidade_destino='Matriz',
            justificativa='Teste integral',
        )
        cls.pedido = PedidoCompra.objects.create(
            solicitacao=cls.solicitacao,
            fornecedor='Fornecedor Teste',
            valor_unitario='15.00',
            valor_total='30.00',
            status='aguardando_aprovacao',
        )
        cls.equipamento = EquipamentoProtecao.objects.create(
            nome='Capacete Teste',
            numero_ca='12345',
            dias_durabilidade=30,
            estoque_atual=5,
        )
        cls.registro_epi = RegistroEPI.objects.create(
            colaborador=cls.colaborador,
            equipamento=cls.equipamento,
            quantidade=1,
            data_movimentacao=date.today(),
            registrado_por=cls.user,
        )
        cls.ativo = Ativo.objects.create(
            numero_patrimonio='PAT-FULL',
            nome='Ativo Teste',
            unidade_atual='Matriz',
            status='manutencao',
        )
        cls.manutencao = RegistroManutencao.objects.create(
            ativo=cls.ativo,
            unidade_origem='Matriz',
            motivo='Teste integral',
            data_inicio=date.today(),
            status='andamento',
            registrado_por=cls.user,
        )
        cls.documento_financeiro = DocumentoFinanceiro.objects.create(
            tipo='nota_fiscal',
            numero_documento='NF-FULL',
            descricao='Documento de teste',
            valor='100.00',
            centro_custo='TESTE',
            unidade='Matriz',
            cnpj_emitente='00.000.000/0001-00',
            razao_social_emitente='Fornecedor Teste',
            data_emissao=date.today(),
            status='aprovado_lancamento',
            recebido_por=cls.user,
            arquivo_pdf=b'%PDF-1.4 teste',
        )
        cls.lancamento = LancamentoERP.objects.create(
            documento=cls.documento_financeiro,
            descricao='Lancamento de teste',
            tipo='debito',
            valor='100.00',
            centro_custo='TESTE',
            competencia=date.today().replace(day=1),
            status='em_validacao',
            lancado_por=cls.user,
        )
        cls.aprovacao = AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(cls.demanda),
            object_id=cls.demanda.pk,
            modulo='administrativo',
            nivel=1,
            titulo='Aprovacao de teste',
            solicitado_por=cls.user,
        )
        cls.notificacao = Notificacao.objects.create(
            destinatario=cls.user,
            titulo='Notificacao de teste',
            mensagem='Teste integral',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _application_route_names(self, patterns=None):
        names = set()
        patterns = patterns or get_resolver().url_patterns
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                if pattern.namespace != 'admin':
                    names.update(self._application_route_names(pattern.url_patterns))
            elif pattern.name:
                names.add(pattern.name)
        return names

    def test_todas_as_paginas_e_endpoints_get(self):
        expected_routes = (
            ('admin:index', (), 200),
            ('login', (), 302),
            ('csrf_token_json', (), 200),
            ('logout', (), 405),
            ('dashboard', (), 200),
            ('notificacoes_json', (), 200),
            ('marcar_lida', (self.notificacao.pk,), 405),
            ('aprovacoes_pendentes', (), 200),
            ('aprovar_registro', (self.aprovacao.pk,), 405),
            ('rejeitar_registro', (self.aprovacao.pk,), 405),
            ('detalhe_aprovacao', (self.aprovacao.pk,), 200),
            ('aprovacoes_count_api', (), 200),
            ('painel_mobile', (), 200),
            ('status_mobile', (), 200),
            ('marcar_notificacoes_mobile', (), 405),
            ('detalhe_aprovacao_mobile', (self.aprovacao.pk,), 200),
            ('pwa_manifest', (), 200),
            ('service_worker', (), 200),
            ('auditoria_sistema', (), 200),
            ('painel_sla', (), 200),
            ('lista_vagas', (), 200),
            ('nova_vaga', (), 200),
            ('detalhe_vaga', (self.vaga.pk,), 200),
            ('adicionar_candidato', (self.vaga.pk,), 200),
            ('avancar_etapa', (self.candidato.pk,), 200),
            ('banco_talentos', (), 200),
            ('parse_curriculo', (), 400),
            ('presign_upload', (), 405),
            ('baixar_curriculo_candidato', (self.candidato.pk,), 200),
            ('baixar_curriculo_talento', (self.talento.pk,), 200),
            ('lista_admissoes', (), 200),
            ('detalhe_admissao', (self.admissao.pk,), 200),
            ('avancar_admissao', (self.admissao.pk,), 405),
            (
                'atualizar_documento',
                (self.admissao.pk, self.documento_admissional.pk),
                200,
            ),
            (
                'baixar_documento',
                (self.admissao.pk, self.documento_admissional.pk),
                200,
            ),
            ('lista_colaboradores', (), 200),
            ('novo_colaborador', (), 200),
            ('editar_colaborador', (self.colaborador.pk,), 200),
            ('excluir_colaborador', (self.colaborador.pk,), 200),
            ('controle_presenca', (), 200),
            ('exportar_presenca_csv', (), 400),
            ('periodo_experiencia', (), 200),
            ('lista_demandas', (), 200),
            ('nova_demanda', (), 200),
            ('detalhe_demanda', (self.demanda.pk,), 200),
            ('atualizar_status_demanda', (self.demanda.pk,), 405),
            ('painel_compras', (), 200),
            ('lista_materiais', (), 200),
            ('nova_solicitacao', (), 200),
            ('detalhe_solicitacao', (self.solicitacao.pk,), 200),
            ('criar_pedido', (self.solicitacao.pk,), 200),
            ('aprovar_pedido', (self.pedido.pk,), 200),
            ('dashboard_sesmet', (), 200),
            ('registrar_epi', (), 200),
            ('registrar_epi_colaborador', (self.colaborador.pk,), 200),
            ('assinar_epi', (self.registro_epi.pk,), 200),
            ('recibo_epi', (self.registro_epi.pk,), 200),
            ('matriz_epis', (), 200),
            ('emitir_os', (self.colaborador.pk,), 200),
            ('catalogo_equipamentos', (), 200),
            ('novo_equipamento', (), 200),
            ('editar_equipamento', (self.equipamento.pk,), 200),
            ('painel_financeiro', (), 200),
            ('entrada_documento', (), 200),
            ('detalhe_documento', (self.documento_financeiro.pk,), 200),
            ('auditoria_documento', (self.documento_financeiro.pk,), 200),
            ('lancar_erp', (self.documento_financeiro.pk,), 200),
            ('validar_lancamento', (self.lancamento.pk,), 200),
            ('download_pdf_financeiro', (self.documento_financeiro.pk,), 200),
            ('extrair_ocr_documento', (), 400),
            ('painel_manutencao', (), 200),
            ('lista_ativos', (), 200),
            ('novo_ativo', (), 200),
            ('editar_ativo', (self.ativo.pk,), 200),
            ('lista_manutencoes', (), 200),
            ('nova_manutencao', (), 200),
            ('concluir_manutencao', (self.manutencao.pk,), 200),
        )

        for route_name, args, expected_status in expected_routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name, args=args))
                self.assertEqual(response.status_code, expected_status)

        tested_names = {name for name, _args, _status in expected_routes}
        tested_names.discard('admin:index')
        self.assertSetEqual(tested_names, self._application_route_names())

        export_response = self.client.get(
            reverse('exportar_presenca_csv'),
            {'data': date.today().isoformat()},
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response['Content-Type'], 'text/csv')

    def test_formularios_rejeitam_dados_incompletos_sem_erro_interno(self):
        post_routes = (
            ('marcar_lida', (self.notificacao.pk,)),
            ('marcar_notificacoes_mobile', ()),
            ('aprovar_registro', (self.aprovacao.pk,)),
            ('rejeitar_registro', (self.aprovacao.pk,)),
            ('nova_vaga', ()),
            ('adicionar_candidato', (self.vaga.pk,)),
            ('avancar_etapa', (self.candidato.pk,)),
            ('parse_curriculo', ()),
            (
                'atualizar_documento',
                (self.admissao.pk, self.documento_admissional.pk),
            ),
            ('avancar_admissao', (self.admissao.pk,)),
            ('novo_colaborador', ()),
            ('editar_colaborador', (self.colaborador.pk,)),
            ('excluir_colaborador', (self.colaborador.pk,)),
            ('controle_presenca', ()),
            ('nova_demanda', ()),
            ('atualizar_status_demanda', (self.demanda.pk,)),
            ('nova_solicitacao', ()),
            ('criar_pedido', (self.solicitacao.pk,)),
            ('aprovar_pedido', (self.pedido.pk,)),
            ('registrar_epi', ()),
            ('registrar_epi_colaborador', (self.colaborador.pk,)),
            ('assinar_epi', (self.registro_epi.pk,)),
            ('emitir_os', (self.colaborador.pk,)),
            ('novo_equipamento', ()),
            ('editar_equipamento', (self.equipamento.pk,)),
            ('entrada_documento', ()),
            ('extrair_ocr_documento', ()),
            ('auditoria_documento', (self.documento_financeiro.pk,)),
            ('lancar_erp', (self.documento_financeiro.pk,)),
            ('validar_lancamento', (self.lancamento.pk,)),
            ('novo_ativo', ()),
            ('editar_ativo', (self.ativo.pk,)),
            ('nova_manutencao', ()),
            ('concluir_manutencao', (self.manutencao.pk,)),
            ('logout', ()),
        )

        for route_name, args in post_routes:
            with self.subTest(route=route_name):
                self.client.force_login(self.user)
                response = self.client.post(reverse(route_name, args=args), {})
                self.assertLess(response.status_code, 500)
