import base64
import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from administrativo.models import DemandaAdministrativa
from admissional.models import Admissao, Colaborador, DocumentoAdmissional
from compras.models import Material, PedidoCompra, SolicitacaoMaterial
from core.models import AprovacaoRegistro, PerfilUsuario
from financeiro.models import AuditoriaItem, DocumentoFinanceiro, LancamentoERP
from manutencao.models import Ativo, RegistroManutencao
from recrutamento.models import Candidato, Talento, Vaga
from sesmet.models import EquipamentoProtecao, RegistroEPI


PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'
    '+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


def pdf_upload(name='documento.pdf'):
    return SimpleUploadedFile(
        name,
        b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF',
        content_type='application/pdf',
    )


def image_upload(name='foto.png'):
    return SimpleUploadedFile(name, PNG_BYTES, content_type='image/png')


class OperationalEndToEndTests(TestCase):
    """Executa jornadas completas pelas mesmas views usadas na interface."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='qa-admin',
            email='qa-admin@example.com',
            password='senha-forte-123',
            first_name='QA',
            last_name='Admin',
        )
        PerfilUsuario.objects.create(usuario=self.user, perfil='admin')
        self.adriana = User.objects.create_user('adriana', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.adriana, perfil='gestor')
        self.ceo = User.objects.create_superuser('ceo_premium', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.ceo, perfil='gestor')
        self.client.force_login(self.user)

    def _aprovar_compras_em_dois_niveis(self, objeto):
        modelo = objeto._meta.model_name
        nivel_um = AprovacaoRegistro.objects.get(
            content_type__model=modelo, object_id=objeto.pk, nivel=1
        )
        self.client.force_login(self.adriana)
        self.client.post(reverse('aprovar_registro', args=[nivel_um.pk]))
        nivel_dois = AprovacaoRegistro.objects.get(
            content_type__model=modelo, object_id=objeto.pk, nivel=2
        )
        self.client.force_login(self.ceo)
        self.client.post(reverse('aprovar_registro', args=[nivel_dois.pk]))
        self.client.force_login(self.user)

    def _create_colaborador(self, suffix='01'):
        return Colaborador.objects.create(
            nome=f'Colaborador QA {suffix}',
            cpf=f'100.200.300-{suffix}',
            email=f'colaborador-{suffix}@example.com',
            telefone='11999999999',
            cargo='Operador',
            unidade='Matriz',
            data_admissao=date.today(),
        )

    def test_recrutamento_admissao_e_cadastro_de_colaborador(self):
        response = self.client.post(reverse('nova_vaga'), {
            'nome_vaga': 'Operador de Logistica QA',
            'quantidade_colaboradores': '1',
            'cidade': 'Sao Paulo',
            'unidade': 'Matriz',
            'perfil_desejado': 'Perfil operacional',
            'atividades': 'Separacao e conferencia',
            'horario_trabalho': '08:00-17:00',
            'tipo_contratacao': 'clt',
            'valor_salario': '2500.00',
            'previsao_inicio': (date.today() + timedelta(days=10)).isoformat(),
            'motivo_solicitacao': 'Aumento de demanda',
            'gestor_responsavel': 'Gestor QA',
        })
        self.assertEqual(response.status_code, 302)
        vaga = Vaga.objects.get(nome_vaga='Operador de Logistica QA')

        response = self.client.post(
            reverse('adicionar_candidato', args=[vaga.pk]),
            {
                'nome': 'Candidato Jornada QA',
                'email': 'candidato-jornada@example.com',
                'telefone': '11988888888',
                'cidade': 'Sao Paulo',
                'cpf_cnpj': '123.456.789-00',
                'curriculum_obs': 'Experiencia comprovada',
                'curriculo_pdf': pdf_upload('curriculo-candidato.pdf'),
            },
        )
        self.assertEqual(response.status_code, 302)
        candidato = Candidato.objects.get(email='candidato-jornada@example.com')
        talento = Talento.objects.get(email=candidato.email)
        self.assertTrue(candidato.arquivo.name.startswith(
            f'recrutamento/vagas/{vaga.pk}/candidatos/{candidato.pk}/curriculo/'
        ))
        self.assertTrue(talento.arquivo.name.startswith(
            f'recrutamento/talentos/{talento.pk}/curriculo/'
        ))

        for observacao in ('Triagem aprovada', 'Perfil aprovado', 'Entrevista aprovada'):
            response = self.client.post(
                reverse('avancar_etapa', args=[candidato.pk]),
                {'acao': 'avancar', 'obs': observacao},
            )
            self.assertEqual(response.status_code, 302)
        candidato.refresh_from_db()
        self.assertEqual(candidato.etapa_atual, 'aprovado')
        self.assertTrue(candidato.encaminhado_admissao)
        admissao = Admissao.objects.get(candidato_email=candidato.email)
        self.assertGreater(admissao.documentos.count(), 10)

        response = self.client.post(reverse('novo_colaborador'), {
            'nome': 'Funcionario Jornada QA',
            'cpf': '987.654.321-00',
            'email': 'funcionario-jornada@example.com',
            'telefone': '11977777777',
            'tipo_contrato': 'clt',
            'cargo': 'Operador de Logistica',
            'setor': 'Operacoes',
            'unidade': 'Matriz',
            'marca': 'eco_premium',
            'data_admissao': date.today().isoformat(),
            'status': 'ativo',
            'anexo_cpf': pdf_upload('cpf-funcionario.pdf'),
        })
        self.assertEqual(response.status_code, 302)
        colaborador = Colaborador.objects.get(email='funcionario-jornada@example.com')
        self.assertTrue(colaborador.anexo_cpf.name.startswith(
            f'admissional/colaboradores/{colaborador.pk}/documentos/anexo_cpf/'
        ))

    def test_material_solicitacao_pedido_e_aprovacao_de_compra(self):
        response = self.client.post(reverse('novo_material'), {
            'nome': 'Papel A4 Jornada QA',
            'foto': image_upload('papel-a4.png'),
            'descricao': 'Caixa com folhas A4',
            'categoria': 'escritorio',
            'unidade_medida': 'cx',
            'quantidade_estoque': '1',
            'estoque_minimo': '2',
            'preco_unitario': '25.00',
            'fornecedor_preferencial': 'Fornecedor QA',
            'localizacao': 'A-01',
        })
        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(nome='Papel A4 Jornada QA')
        self.assertRegex(material.codigo, r'^MAT-\d{6}$')
        self.assertTrue(material.foto.name.startswith(
            f'compras/materiais/{material.pk}/foto/'
        ))

        response = self.client.post(reverse('nova_solicitacao'), {
            'material': str(material.pk),
            'quantidade_solicitada': '5',
            'unidade_destino': 'Filial QA',
            'justificativa': 'Reposicao mensal',
        })
        self.assertEqual(response.status_code, 302)
        solicitacao = SolicitacaoMaterial.objects.get(material=material)
        self.assertEqual(solicitacao.status, 'pendente')
        self._aprovar_compras_em_dois_niveis(solicitacao.requisicao)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, 'compra_externa')

        response = self.client.post(
            reverse('criar_pedido', args=[solicitacao.pk]),
            {
                'fornecedor': 'Distribuidora QA',
                'cnpj_fornecedor': '00.000.000/0001-00',
                'valor_unitario': '30',
                'prazo_entrega': (date.today() + timedelta(days=5)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        pedido = PedidoCompra.objects.get(solicitacao=solicitacao)
        self.assertEqual(str(pedido.valor_total), '150.00')
        self.assertRegex(pedido.numero_pedido, r'^PC-\d{6}$')

        self._aprovar_compras_em_dois_niveis(pedido)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'pedido_emitido')
        self.assertEqual(pedido.aprovado_por, self.ceo)

    def test_pedido_aceita_valor_unitario_com_duas_casas_decimais(self):
        material = Material.objects.create(
            nome='Material Decimal QA', quantidade_estoque=0
        )
        solicitacao = SolicitacaoMaterial.objects.create(
            material=material,
            quantidade_solicitada='5.00',
            solicitante='QA Admin',
            solicitante_usuario=self.user,
            unidade_destino='Matriz',
            justificativa='Validar casas decimais',
            status='compra_externa',
        )

        response = self.client.post(
            reverse('criar_pedido', args=[solicitacao.pk]),
            {'fornecedor': 'Fornecedor Decimal', 'valor_unitario': '30.00'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(PedidoCompra.objects.filter(solicitacao=solicitacao).exists())
        self.assertEqual(
            PedidoCompra.objects.get(solicitacao=solicitacao).valor_total,
            Decimal('150.00'),
        )

    def test_epi_assinatura_ativo_e_manutencao(self):
        colaborador = self._create_colaborador('02')
        response = self.client.post(reverse('novo_equipamento'), {
            'nome': 'Capacete Jornada QA',
            'foto': image_upload('capacete.png'),
            'numero_ca': 'CA-12345',
            'fabricante': 'Fabricante QA',
            'dias_durabilidade': '30',
            'estoque_atual': '10',
        })
        self.assertEqual(response.status_code, 302)
        equipamento = EquipamentoProtecao.objects.get(nome='Capacete Jornada QA')
        self.assertTrue(equipamento.foto.name.startswith(
            f'sesmet/epis/{equipamento.pk}/foto/'
        ))

        response = self.client.post(reverse('registrar_epi'), {
            'colaborador': str(colaborador.pk),
            'equipamento': str(equipamento.pk),
            'tipo_movimentacao': 'retirada',
            'data_movimentacao': date.today().isoformat(),
            'quantidade': '2',
            'obs': 'Entrega de admissao',
        })
        self.assertEqual(response.status_code, 302)
        registro_epi = RegistroEPI.objects.get(colaborador=colaborador)
        equipamento.refresh_from_db()
        self.assertEqual(equipamento.estoque_atual, 8)

        signature = 'data:image/png;base64,' + base64.b64encode(PNG_BYTES).decode()
        response = self.client.post(
            reverse('assinar_epi', args=[registro_epi.pk]),
            {'assinatura_base64': signature},
        )
        self.assertEqual(response.status_code, 302)
        registro_epi.refresh_from_db()
        self.assertTrue(registro_epi.assinado)

        response = self.client.post(reverse('novo_ativo'), {
            'numero_patrimonio': 'PAT-QA-001',
            'nome': 'Empilhadeira Jornada QA',
            'marca': 'Marca QA',
            'modelo': 'Modelo QA',
            'numero_serie': 'SERIE-QA-001',
            'unidade_atual': 'Matriz',
            'status': 'ativo',
            'data_aquisicao': date.today().isoformat(),
            'valor_aquisicao': '50000.00',
            'foto': image_upload('empilhadeira.png'),
        })
        self.assertEqual(response.status_code, 302)
        ativo = Ativo.objects.get(numero_patrimonio='PAT-QA-001')
        self.assertTrue(ativo.foto.name.startswith(
            f'manutencao/ativos/{ativo.pk}/cadastro/foto/'
        ))

        response = self.client.post(reverse('nova_manutencao'), {
            'ativo': str(ativo.pk),
            'unidade_origem': 'Matriz',
            'motivo': 'Revisao preventiva',
            'data_inicio': date.today().isoformat(),
            'fornecedor_servico': 'Oficina QA',
        })
        self.assertEqual(response.status_code, 302)
        manutencao = RegistroManutencao.objects.get(ativo=ativo)
        ativo.refresh_from_db()
        self.assertEqual(ativo.status, 'manutencao')
        self.assertTrue(AprovacaoRegistro.objects.filter(
            object_id=manutencao.pk, modulo='manutencao'
        ).exists())

        response = self.client.post(
            reverse('concluir_manutencao', args=[manutencao.pk]),
            {
                'status': 'concluida',
                'data_conclusao': date.today().isoformat(),
                'fornecedor_servico': 'Oficina QA',
                'custo_reparo': '500.00',
                'unidade_retorno': 'Matriz',
                'obs': 'Revisao concluida',
            },
        )
        self.assertEqual(response.status_code, 302)
        manutencao.refresh_from_db()
        ativo.refresh_from_db()
        self.assertEqual(manutencao.status, 'concluida')
        self.assertEqual(ativo.status, 'ativo')

    def test_documento_financeiro_auditoria_lancamento_e_validacao(self):
        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'nota_fiscal',
            'numero_documento': 'NF-QA-001',
            'descricao': 'Compra de material QA',
            'valor': '150.00',
            'centro_custo': 'OPERACOES',
            'unidade': 'Matriz',
            'cnpj_emitente': '00.000.000/0001-00',
            'razao_social_emitente': 'Distribuidora QA',
            'data_emissao': date.today().isoformat(),
            'arquivo_pdf': pdf_upload('nota-fiscal-qa.pdf'),
            'produtos_json': json.dumps([{
                'descricao_produto': 'Papel A4',
                'ncm': '4802',
                'quantidade': 5,
                'valor_unitario': 30,
                'valor_total': 150,
            }]),
        })
        self.assertEqual(response.status_code, 302)
        documento = DocumentoFinanceiro.objects.get(numero_documento='NF-QA-001')
        self.assertTrue(documento.arquivo.name.startswith(
            f'financeiro/documentos/{date.today():%Y/%m}/{documento.pk}/nota_fiscal/'
        ))
        self.assertEqual(documento.itens.count(), 1)
        self.assertEqual(documento.auditoria.count(), len(AuditoriaItem.ITENS_CHECKLIST))

        audit_data = {}
        for item in documento.auditoria.all():
            audit_data[f'item_{item.pk}'] = 'ok'
            audit_data[f'obs_{item.pk}'] = 'Conferido no teste integral'
        response = self.client.post(
            reverse('auditoria_documento', args=[documento.pk]), audit_data
        )
        self.assertEqual(response.status_code, 302)
        documento.refresh_from_db()
        self.assertEqual(documento.status, 'aprovado_lancamento')

        response = self.client.post(
            reverse('lancar_erp', args=[documento.pk]),
            {
                'descricao': 'Lancamento NF-QA-001',
                'tipo': 'debito',
                'competencia': date.today().replace(day=1).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        lancamento = LancamentoERP.objects.get(documento=documento)
        self.assertEqual(lancamento.status, 'em_validacao')

        response = self.client.post(
            reverse('validar_lancamento', args=[lancamento.pk]),
            {'acao': 'validar'},
        )
        self.assertEqual(response.status_code, 302)
        lancamento.refresh_from_db()
        documento.refresh_from_db()
        self.assertEqual(lancamento.status, 'finalizado')
        self.assertEqual(documento.status, 'arquivado')

    def test_demanda_administrativa_ate_arquivamento(self):
        response = self.client.post(reverse('nova_demanda'), {
            'tipo': 'contratos',
            'titulo': 'Revisao contratual Jornada QA',
            'descricao': 'Revisar contrato operacional',
            'requisitante': 'Equipe QA',
            'prioridade': 'alta',
        })
        self.assertEqual(response.status_code, 302)
        demanda = DemandaAdministrativa.objects.get(
            titulo='Revisao contratual Jornada QA'
        )
        response = self.client.post(
            reverse('atualizar_status_demanda', args=[demanda.pk]),
            {'status': 'arquivada'},
        )
        self.assertEqual(response.status_code, 302)
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, 'arquivada')
        self.assertIsNotNone(demanda.concluido_em)
