"""
ERP Grupo PremiumBR — Management Command: populate_seed
Popula o banco de dados com dados de demonstração para apresentação.
Uso: python manage.py populate_seed
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
import random


class Command(BaseCommand):
    help = 'Popula o banco de dados com dados de demonstração do ERP Grupo PremiumBR'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Iniciando seed de demonstração do ERP Grupo PremiumBR...')

        self._criar_usuarios()
        self._criar_vagas_candidatos()
        self._criar_colaboradores_admissoes()
        self._criar_demandas_administrativas()
        self._criar_materiais_estoque()
        self._criar_documentos_financeiros()

        self.stdout.write(self.style.SUCCESS('✅ Seed concluído com sucesso! O sistema está pronto para demonstração.'))
        self.stdout.write('\n📋 USUÁRIOS CRIADOS:')
        self.stdout.write('  admin          / admin123    (Administrador)')
        self.stdout.write('  ana.gestora    / gestor123   (Gestora)')
        self.stdout.write('  carlos.rh      / rh123       (RH)')
        self.stdout.write('  fernanda.fin   / fin123      (Financeiro)')
        self.stdout.write('  roberto.sesmet / sesmet123   (SESMET)')
        self.stdout.write('  paula.compras  / compras123  (Compras)')

    def _criar_usuarios(self):
        from core.models import PerfilUsuario
        self.stdout.write('  👤 Criando usuários...')

        usuarios = [
            {'username': 'admin',          'first_name': 'Admin',     'last_name': 'ERP',              'email': 'admin@ecopremium.com.br',     'senha': 'admin123',    'perfil': 'admin',      'marca': 'matriz',       'unidade': 'Matriz'},
            {'username': 'ana.gestora',    'first_name': 'Ana',       'last_name': 'Gestora Silva',    'email': 'ana@ecopremium.com.br',        'senha': 'gestor123',   'perfil': 'gestor',     'marca': 'eco_premium',  'unidade': 'São Paulo'},
            {'username': 'carlos.rh',      'first_name': 'Carlos',    'last_name': 'RH Santos',        'email': 'carlos@ecopremium.com.br',     'senha': 'rh123',       'perfil': 'rh',         'marca': 'trip_premium', 'unidade': 'São Paulo'},
            {'username': 'fernanda.fin',   'first_name': 'Fernanda',  'last_name': 'Fiscal Oliveira',  'email': 'fernanda@ecopremium.com.br',   'senha': 'fin123',      'perfil': 'financeiro', 'marca': 'log_premium',  'unidade': 'Curitiba'},
            {'username': 'roberto.sesmet', 'first_name': 'Roberto',   'last_name': 'Segurança Costa',  'email': 'roberto@ecopremium.com.br',    'senha': 'sesmet123',   'perfil': 'sesmet',     'marca': 'eco_premium',  'unidade': 'Campinas'},
            {'username': 'paula.compras',  'first_name': 'Paula',     'last_name': 'Compras Lima',     'email': 'paula@ecopremium.com.br',      'senha': 'compras123',  'perfil': 'compras',    'marca': 'trip_premium', 'unidade': 'Guarulhos'},
        ]

        for u in usuarios:
            user, created = User.objects.get_or_create(username=u['username'])
            user.first_name = u['first_name']
            user.last_name = u['last_name']
            user.email = u['email']
            user.set_password(u['senha'])
            if u['perfil'] == 'admin':
                user.is_staff = True
                user.is_superuser = True
            user.save()

            PerfilUsuario.objects.update_or_create(
                usuario=user,
                defaults={
                    'perfil': u['perfil'],
                    'marca': u['marca'],
                    'unidade': u['unidade'],
                }
            )
            if created:
                self.stdout.write(f'    ✓ {user.get_full_name()} ({u["perfil"]})')

    def _criar_vagas_candidatos(self):
        from recrutamento.models import Vaga, Candidato
        from admissional.models import DocumentoAdmissional, Admissao
        from core.models import Notificacao
        self.stdout.write('  👥 Criando vagas e candidatos...')

        gestor = User.objects.get(username='ana.gestora')
        rh = User.objects.get(username='carlos.rh')

        vagas_data = [
            {
                'nome_vaga': 'Operador de Logística',
                'quantidade_colaboradores': 3,
                'cidade': 'São Paulo',
                'unidade': 'Centro de Distribuição SP',
                'perfil_desejado': 'Profissional com experiência em separação e expedição de mercadorias, habilitação AB para condução de empilhadeira.',
                'atividades': 'Separação de pedidos, embalagem, conferência de carga, controle de estoque físico, operação de empilhadeira.',
                'horario_trabalho': '06h00 às 14h20 (Seg-Sáb)',
                'tipo_contratacao': 'clt',
                'valor_salario': '2850.00',
                'previsao_inicio': date.today() + timedelta(days=15),
                'exige_experiencia': True,
                'descricao_experiencia': 'Mínimo 1 ano na função e habilitação para empilhadeira',
                'motivo_solicitacao': 'Expansão da operação de distribuição no centro de SP',
                'gestor_responsavel': 'Ana Gestora Silva',
                'status': 'em_selecao',
            },
            {
                'nome_vaga': 'Auxiliar Administrativo',
                'quantidade_colaboradores': 1,
                'cidade': 'Campinas',
                'unidade': 'Filial Campinas',
                'perfil_desejado': 'Perfil organizado, proativo, com boa comunicação e domínio de pacote Office.',
                'atividades': 'Controle documental, atendimento interno, suporte à gestão, elaboração de relatórios.',
                'horario_trabalho': '08h00 às 17h00 (Seg-Sex)',
                'tipo_contratacao': 'clt',
                'valor_salario': '2200.00',
                'previsao_inicio': date.today() + timedelta(days=7),
                'exige_experiencia': False,
                'descricao_experiencia': '',
                'motivo_solicitacao': 'Substituição de colaborador desligado',
                'gestor_responsavel': 'Ana Gestora Silva',
                'status': 'em_selecao',
            },
            {
                'nome_vaga': 'Motorista Categoria D',
                'quantidade_colaboradores': 2,
                'cidade': 'Guarulhos',
                'unidade': 'Hub Guarulhos',
                'perfil_desejado': 'Motorista com CNH Categoria D, experiência em transporte de cargas, bom relacionamento com cliente.',
                'atividades': 'Entrega de cargas em rotas urbanas e região metropolitana, acompanhamento de NF, pós-venda.',
                'horario_trabalho': '05h30 às 14h00 (Seg-Sáb)',
                'tipo_contratacao': 'clt',
                'valor_salario': '3200.00',
                'previsao_inicio': date.today() + timedelta(days=20),
                'exige_experiencia': True,
                'descricao_experiencia': 'CNH D obrigatória, mínimo 2 anos em função similar',
                'motivo_solicitacao': 'Abertura de novas rotas de entrega',
                'gestor_responsavel': 'Paula Compras Lima',
                'status': 'aguardando_entrevista',
            },
        ]

        vagas = []
        for vd in vagas_data:
            vaga, created = Vaga.objects.get_or_create(
                nome_vaga=vd['nome_vaga'],
                unidade=vd['unidade'],
                defaults={**vd, 'gestor_usuario': gestor}
            )
            vagas.append(vaga)
            if created:
                self.stdout.write(f'    ✓ Vaga: {vaga.nome_vaga}')

        # Candidatos para vaga 1 (Operador de Logística)
        candidatos_v1 = [
            {'nome': 'João Pereira da Silva', 'email': 'joao.pereira@email.com', 'telefone': '(11) 98765-4321', 'cpf': '123.456.789-01', 'etapa_atual': 'triagem'},
            {'nome': 'Maria Fernanda Costa', 'email': 'maria.costa@email.com', 'telefone': '(11) 91234-5678', 'cpf': '234.567.890-12', 'etapa_atual': 'avaliacao_dp'},
            {'nome': 'Pedro Alves Rodrigues', 'email': 'pedro.alves@email.com', 'telefone': '(11) 94567-8901', 'cpf': '345.678.901-23', 'etapa_atual': 'entrevista_final'},
            {'nome': 'Lucas Mendes Souza', 'email': 'lucas.mendes@email.com', 'telefone': '(11) 97890-1234', 'cpf': '456.789.012-34', 'etapa_atual': 'aprovado', 'aprovado': True, 'encaminhado_admissao': True},
        ]

        for cd in candidatos_v1:
            c, created = Candidato.objects.get_or_create(
                email=cd['email'],
                defaults={**cd, 'vaga': vagas[0], 'avaliado_por': rh}
            )
            if created:
                self.stdout.write(f'    ✓ Candidato: {c.nome} ({c.get_etapa_atual_display()})')

        # Candidatos para vaga 2
        c2, created = Candidato.objects.get_or_create(
            email='carla.admin@email.com',
            defaults={
                'vaga': vagas[1], 'nome': 'Carla Rodrigues Pinto',
                'email': 'carla.admin@email.com', 'telefone': '(19) 93456-7890',
                'etapa_atual': 'triagem', 'avaliado_por': rh
            }
        )

        # Criar processo admissional para o candidato aprovado (Lucas)
        lucas = Candidato.objects.filter(nome='Lucas Mendes Souza').first()
        if lucas:
            adm, created = Admissao.objects.get_or_create(
                candidato_email=lucas.email,
                defaults={
                    'candidato_nome': lucas.nome,
                    'candidato_telefone': lucas.telefone,
                    'vaga_nome': lucas.vaga.nome_vaga,
                    'unidade_destino': lucas.vaga.unidade,
                    'status': 'documentos_em_analise',
                    'responsavel_rh': rh,
                }
            )
            if created:
                # Criar checklist de documentos
                tipos = [t[0] for t in DocumentoAdmissional.TIPOS]
                for i, tipo in enumerate(tipos):
                    status = 'aprovado' if i < 7 else 'pendente'
                    DocumentoAdmissional.objects.get_or_create(
                        admissao=adm, tipo=tipo,
                        defaults={'status': status}
                    )
                self.stdout.write(f'    ✓ Admissão criada para: {lucas.nome}')

            # Notificação demo
            Notificacao.objects.get_or_create(
                destinatario=rh,
                titulo=f'🔔 Candidato aprovado: {lucas.nome}',
                defaults={
                    'tipo': 'gateway',
                    'modulo': 'admissional',
                    'mensagem': f'Candidato {lucas.nome} foi aprovado para a vaga "Operador de Logística". Processo admissional criado automaticamente.',
                    'url_acao': f'/admissional/{adm.pk}/' if adm else '/admissional/',
                }
            )

    def _criar_colaboradores_admissoes(self):
        from admissional.models import Colaborador, Admissao, DocumentoAdmissional
        from sesmet.models import RegistroEPI, OrdemServico, IntegracaoSeguranca
        self.stdout.write('  🏢 Criando colaboradores e EPIs...')

        rh = User.objects.get(username='carlos.rh')
        sesmet = User.objects.get(username='roberto.sesmet')
        hoje = date.today()

        colaboradores_data = [
            {
                'nome': 'Rafael Souza Barbosa', 'cpf': '001.234.567-89', 'rg': '12.345.678-9',
                'data_nascimento': date(1992, 3, 15),
                'email': 'rafael.souza@ecopremium.com.br', 'telefone': '(11) 99876-5432',
                'cargo': 'Operador de Logística', 'setor': 'Operacional', 'unidade': 'Centro de Distribuição SP',
                'marca': 'eco_premium', 'data_admissao': hoje - timedelta(days=90),
                'status': 'ativo', 'salario': 2850.00,
                'pis_pasep': '123.45678.90-1', 'ctps': '12345 / Série 001',
            },
            {
                'nome': 'Beatriz Almeida Ferreira', 'cpf': '002.345.678-90', 'rg': '23.456.789-0',
                'data_nascimento': date(1995, 7, 22),
                'email': 'beatriz.almeida@ecopremium.com.br', 'telefone': '(11) 98765-1234',
                'cargo': 'Auxiliar Administrativo', 'setor': 'Administrativo', 'unidade': 'Filial Campinas',
                'marca': 'trip_premium', 'data_admissao': hoje - timedelta(days=45),
                'status': 'ativo', 'salario': 2200.00,
                'pis_pasep': '234.56789.01-2', 'ctps': '23456 / Série 002',
            },
            {
                'nome': 'Marcos Vinícius Teixeira', 'cpf': '003.456.789-01', 'rg': '34.567.890-1',
                'data_nascimento': date(1988, 11, 5),
                'email': 'marcos.teixeira@ecopremium.com.br', 'telefone': '(11) 97654-3210',
                'cargo': 'Motorista Cat. D', 'setor': 'Transporte', 'unidade': 'Hub Guarulhos',
                'marca': 'log_premium', 'data_admissao': hoje - timedelta(days=180),
                'status': 'ativo', 'salario': 3200.00,
                'pis_pasep': '345.67890.12-3', 'ctps': '34567 / Série 003',
            },
        ]

        for cd in colaboradores_data:
            colab, created = Colaborador.objects.get_or_create(cpf=cd['cpf'], defaults=cd)
            if not created:
                continue
            self.stdout.write(f'    ✓ Colaborador: {colab.nome}')

            # EPIs para cada colaborador
            epis_config = [
                {'tipo_epi': 'luva', 'motivo': 'inicial', 'dias_atras': 25, 'num_ca': 'CA-12345'},
                {'tipo_epi': 'calcado', 'motivo': 'inicial', 'dias_atras': 90, 'num_ca': 'CA-23456'},
                {'tipo_epi': 'protetor_auricular', 'motivo': 'inicial', 'dias_atras': 80, 'num_ca': 'CA-34567'},
                {'tipo_epi': 'oculos', 'motivo': 'inicial', 'dias_atras': 90, 'num_ca': 'CA-45678'},
                {'tipo_epi': 'uniforme', 'motivo': 'inicial', 'dias_atras': 90, 'num_ca': ''},
            ]
            for ep in epis_config:
                data_ent = hoje - timedelta(days=ep['dias_atras'])
                epi, _ = RegistroEPI.objects.get_or_create(
                    colaborador=colab,
                    tipo_epi=ep['tipo_epi'],
                    data_entrega=data_ent,
                    defaults={
                        'quantidade': 1,
                        'numero_ca': ep['num_ca'],
                        'motivo_substituicao': ep['motivo'],
                        'assinado': True,
                        'registrado_por': sesmet,
                    }
                )

            # OS para cada colaborador
            os_count = OrdemServico.objects.count() + 1
            OrdemServico.objects.get_or_create(
                colaborador=colab,
                numero=f'OS-{os_count:04d}',
                defaults={
                    'descricao_riscos': 'Risco de queda de objetos, acidentes com empilhadeiras, ruído excessivo.',
                    'medidas_preventivas': 'Uso obrigatório de EPIs, sinalização das áreas de risco, treinamento regular.',
                    'epis_obrigatorios': 'Capacete, luvas, calçado de segurança, protetor auricular, óculos.',
                    'data_emissao': colab.data_admissao,
                    'assinado': True,
                    'data_assinatura': colab.data_admissao,
                    'emitido_por': sesmet,
                }
            )

            # Integração
            IntegracaoSeguranca.objects.get_or_create(
                colaborador=colab,
                defaults={
                    'data_integracao': colab.data_admissao,
                    'apresentador': 'Roberto Segurança Costa',
                    'missao_visao_valores': True,
                    'normas_seguranca': True,
                    'uso_epis': True,
                    'procedimentos_emergencia': True,
                    'concluida': True,
                }
            )

        # EPI vencido para demonstração (respirador P2 — validade 3 dias)
        rafael = Colaborador.objects.filter(cpf='001.234.567-89').first()
        if rafael:
            RegistroEPI.objects.get_or_create(
                colaborador=rafael,
                tipo_epi='respirador_p2',
                data_entrega=hoje - timedelta(days=10),
                defaults={
                    'quantidade': 2,
                    'numero_ca': 'CA-56789',
                    'motivo_substituicao': 'inicial',
                    'assinado': True,
                    'registrado_por': sesmet,
                }
            )

    def _criar_demandas_administrativas(self):
        from administrativo.models import DemandaAdministrativa
        self.stdout.write('  🗂️ Criando demandas administrativas...')

        admin_user = User.objects.get(username='ana.gestora')
        hoje = timezone.now()

        demandas = [
            {
                'tipo': 'contratos', 'titulo': 'Renovação de Contrato — Transportadora Veloz Ltda',
                'descricao': 'Contrato de prestação de serviços de transporte vence em 30 dias. Necessário iniciar processo de renovação e renegociação de valores.',
                'requisitante': 'Ana Gestora Silva', 'prioridade': 'alta', 'status': 'em_execucao',
            },
            {
                'tipo': 'reembolsos', 'titulo': 'Reembolso — Viagem Roberto Costa (Campinas)',
                'descricao': 'Solicitação de reembolso de despesas de viagem: combustível R$245,00 + pedágio R$87,50 + refeição R$68,00. Total: R$400,50.',
                'requisitante': 'Roberto Segurança Costa', 'prioridade': 'media', 'status': 'em_triagem',
            },
            {
                'tipo': 'relatorios', 'titulo': 'Relatório Mensal de Indicadores Operacionais — Maio/2025',
                'descricao': 'Compilação dos KPIs mensais: absenteísmo, produtividade, acidentes, entregas realizadas, SLA por unidade.',
                'requisitante': 'Ana Gestora Silva', 'prioridade': 'alta', 'status': 'em_execucao',
            },
            {
                'tipo': 'agendas_reunioes', 'titulo': 'Reunião de Alinhamento Operacional — Todas as Unidades',
                'descricao': 'Agendar reunião mensal de alinhamento com gestores de todas as unidades. Data sugerida: primeira semana do mês.',
                'requisitante': 'Ana Gestora Silva', 'prioridade': 'media', 'status': 'recebida',
            },
            {
                'tipo': 'apoio_operacional', 'titulo': 'URGENTE: Falta de material de escritório — Filial Campinas',
                'descricao': 'Filial Campinas está sem papel A4, cartuchos de impressora e envelopes. Necessidade imediata para expediente.',
                'requisitante': 'Beatriz Almeida Ferreira', 'prioridade': 'urgente', 'status': 'em_triagem',
            },
            {
                'tipo': 'controle_documental', 'titulo': 'Organização de Arquivos Físicos — Documentos 2023',
                'descricao': 'Digitalização e arquivamento dos documentos físicos do exercício 2023 conforme política de retenção documental.',
                'requisitante': 'Carlos RH Santos', 'prioridade': 'baixa', 'status': 'arquivada',
            },
        ]

        for d in demandas:
            dem, created = DemandaAdministrativa.objects.get_or_create(
                titulo=d['titulo'],
                defaults={**d, 'requisitante_usuario': admin_user}
            )
            if created and d['status'] == 'arquivada':
                dem.concluido_em = hoje - timedelta(days=5)
                dem.save()
            if created:
                self.stdout.write(f'    ✓ Demanda: {dem.titulo[:50]}...')

    def _criar_materiais_estoque(self):
        from compras.models import Material, SolicitacaoMaterial, PedidoCompra
        self.stdout.write('  🛒 Criando materiais e estoque...')

        compras_user = User.objects.get(username='paula.compras')
        hoje = date.today()

        materiais = [
            {'codigo': 'MAT-001', 'nome': 'Luva Nitrilica M', 'categoria': 'epi', 'unidade_medida': 'pr', 'quantidade_estoque': 15, 'estoque_minimo': 20, 'preco_unitario': 8.50, 'localizacao': 'Prateleira A1'},
            {'codigo': 'MAT-002', 'nome': 'Protetor Auricular Espuma', 'categoria': 'epi', 'unidade_medida': 'un', 'quantidade_estoque': 50, 'estoque_minimo': 30, 'preco_unitario': 3.20, 'localizacao': 'Prateleira A2'},
            {'codigo': 'MAT-003', 'nome': 'Respirador PFF2 (P2)', 'categoria': 'epi', 'unidade_medida': 'cx', 'quantidade_estoque': 2, 'estoque_minimo': 5, 'preco_unitario': 45.00, 'localizacao': 'Prateleira A3'},
            {'codigo': 'MAT-004', 'nome': 'Papel A4 (Resma 500 fls)', 'categoria': 'escritorio', 'unidade_medida': 'pc', 'quantidade_estoque': 3, 'estoque_minimo': 10, 'preco_unitario': 28.90, 'localizacao': 'Almoxarifado B1'},
            {'codigo': 'MAT-005', 'nome': 'Cartucho Impressora HP 664', 'categoria': 'escritorio', 'unidade_medida': 'un', 'quantidade_estoque': 1, 'estoque_minimo': 4, 'preco_unitario': 67.50, 'localizacao': 'Almoxarifado B2'},
            {'codigo': 'MAT-006', 'nome': 'Álcool 70% (Galão 5L)', 'categoria': 'limpeza', 'unidade_medida': 'un', 'quantidade_estoque': 8, 'estoque_minimo': 5, 'preco_unitario': 42.00, 'localizacao': 'Almoxarifado C1'},
            {'codigo': 'MAT-007', 'nome': 'Caixa de Papelão 40x30x20', 'categoria': 'outros', 'unidade_medida': 'un', 'quantidade_estoque': 200, 'estoque_minimo': 100, 'preco_unitario': 2.80, 'localizacao': 'Galpão D1'},
            {'codigo': 'MAT-008', 'nome': 'Fita Adesiva Embalagem 45mm', 'categoria': 'outros', 'unidade_medida': 'rl', 'quantidade_estoque': 25, 'estoque_minimo': 15, 'preco_unitario': 4.50, 'localizacao': 'Galpão D2'},
            {'codigo': 'MAT-009', 'nome': 'Óleo Lubrificante 20W50 (4L)', 'categoria': 'manutencao', 'unidade_medida': 'un', 'quantidade_estoque': 6, 'estoque_minimo': 4, 'preco_unitario': 35.00, 'localizacao': 'Manutenção E1'},
            {'codigo': 'MAT-010', 'nome': 'Sapato de Segurança Nr 42', 'categoria': 'epi', 'unidade_medida': 'pr', 'quantidade_estoque': 4, 'estoque_minimo': 5, 'preco_unitario': 189.90, 'localizacao': 'Prateleira A4'},
        ]

        mats = []
        for m in materiais:
            mat, created = Material.objects.get_or_create(codigo=m['codigo'], defaults=m)
            mats.append(mat)
            if created:
                self.stdout.write(f'    ✓ Material: {mat.nome} (estoque: {mat.quantidade_estoque})')

        # Solicitações de exemplo
        solic_data = [
            {'material': mats[0], 'quantidade': 30, 'unidade': 'Centro de Distribuição SP', 'justificativa': 'Reposição mensal de luvas para equipe operacional (15 colaboradores)', 'status': 'compra_externa'},
            {'material': mats[3], 'quantidade': 20, 'unidade': 'Filial Campinas', 'justificativa': 'Estoque crítico — expediente administrativo comprometido', 'status': 'compra_externa'},
            {'material': mats[5], 'quantidade': 3, 'unidade': 'Hub Guarulhos', 'justificativa': 'Higienização periódica dos veículos', 'status': 'atendido_interno'},
        ]

        for sd in solic_data:
            sol, created = SolicitacaoMaterial.objects.get_or_create(
                material=sd['material'],
                solicitante='Paula Compras Lima',
                defaults={
                    'quantidade_solicitada': sd['quantidade'],
                    'solicitante_usuario': compras_user,
                    'unidade_destino': sd['unidade'],
                    'justificativa': sd['justificativa'],
                    'status': sd['status'],
                }
            )
            if created:
                self.stdout.write(f'    ✓ Solicitação: {sol.material.nome}')

                # Pedido de compra para solicitações externas
                if sd['status'] == 'compra_externa':
                    PedidoCompra.objects.create(
                        solicitacao=sol,
                        fornecedor='Distribuidora EPI Brasil Ltda' if 'Luva' in sol.material.nome else 'Papelaria Central Ltda',
                        cnpj_fornecedor='12.345.678/0001-90',
                        valor_unitario=sd['material'].preco_unitario or 0,
                        valor_total=(sd['material'].preco_unitario or 0) * float(sd['quantidade']),
                        prazo_entrega=hoje + timedelta(days=7),
                        status='aguardando_aprovacao',
                    )

    def _criar_documentos_financeiros(self):
        from financeiro.models import DocumentoFinanceiro, AuditoriaItem, LancamentoERP
        self.stdout.write('  💰 Criando documentos financeiros...')

        fin_user = User.objects.get(username='fernanda.fin')
        hoje = date.today()

        docs_data = [
            {
                'tipo': 'nota_fiscal', 'numero_documento': 'NF-2025-001847',
                'descricao': 'Fornecimento de EPIs — Distribuidora Segurança Total',
                'valor': 3420.50, 'centro_custo': 'SESMET-SP', 'unidade': 'Centro de Distribuição SP',
                'cnpj_emitente': '45.678.901/0001-23', 'razao_social_emitente': 'Distribuidora Segurança Total Ltda',
                'data_emissao': hoje - timedelta(days=5), 'data_vencimento': hoje + timedelta(days=25),
                'status': 'em_auditoria',
            },
            {
                'tipo': 'nota_fiscal', 'numero_documento': 'NF-2025-002341',
                'descricao': 'Serviços de Manutenção Preventiva de Veículos',
                'valor': 8750.00, 'centro_custo': 'TRANSPORTE-GRU', 'unidade': 'Hub Guarulhos',
                'cnpj_emitente': '56.789.012/0001-34', 'razao_social_emitente': 'Auto Mecânica Rápida Ltda',
                'data_emissao': hoje - timedelta(days=10), 'data_vencimento': hoje + timedelta(days=20),
                'status': 'aprovado_lancamento',
            },
            {
                'tipo': 'pagamento', 'numero_documento': 'PAG-2025-0087',
                'descricao': 'Pagamento Folha de Pagamento — Maio/2025',
                'valor': 42850.00, 'centro_custo': 'RH-GERAL', 'unidade': 'Matriz',
                'cnpj_emitente': '01.234.567/0001-01', 'razao_social_emitente': 'Grupo PremiumBR Holding Ltda',
                'data_emissao': hoje - timedelta(days=2), 'data_vencimento': hoje + timedelta(days=3),
                'status': 'lancado',
            },
            {
                'tipo': 'reembolso', 'numero_documento': 'REM-2025-0034',
                'descricao': 'Reembolso viagem Roberto Costa — Campinas',
                'valor': 400.50, 'centro_custo': 'SESMET-CAM', 'unidade': 'Filial Campinas',
                'cnpj_emitente': '', 'razao_social_emitente': 'Roberto Segurança Costa (PF)',
                'data_emissao': hoje - timedelta(days=3), 'data_vencimento': hoje + timedelta(days=15),
                'status': 'recebido',
            },
            {
                'tipo': 'contrato', 'numero_documento': 'CONT-2025-012',
                'descricao': 'Contrato Prestação Serviços — Transportadora Veloz Ltda',
                'valor': 85000.00, 'centro_custo': 'OPERACIONAL-SP', 'unidade': 'Matriz',
                'cnpj_emitente': '67.890.123/0001-45', 'razao_social_emitente': 'Transportadora Veloz Ltda',
                'data_emissao': hoje - timedelta(days=30), 'data_vencimento': hoje + timedelta(days=335),
                'status': 'arquivado',
            },
        ]

        for dd in docs_data:
            doc, created = DocumentoFinanceiro.objects.get_or_create(
                numero_documento=dd['numero_documento'],
                defaults={**dd, 'recebido_por': fin_user}
            )
            if not created:
                continue
            self.stdout.write(f'    ✓ Documento: {doc.numero_documento} ({doc.get_tipo_display()})')

            # Criar checklist de auditoria
            for item_key, _ in AuditoriaItem.ITENS_CHECKLIST:
                status_item = 'ok' if doc.status in ['aprovado_lancamento', 'lancado', 'arquivado'] else 'pendente'
                AuditoriaItem.objects.get_or_create(
                    documento=doc, item=item_key,
                    defaults={'status': status_item, 'verificado_por': fin_user}
                )

            # Criar lançamento para docs aprovados/lançados
            if doc.status in ['lancado', 'arquivado']:
                lanc, lc = LancamentoERP.objects.get_or_create(
                    documento=doc,
                    defaults={
                        'descricao': doc.descricao,
                        'tipo': 'debito',
                        'valor': doc.valor,
                        'centro_custo': doc.centro_custo,
                        'competencia': doc.data_emissao,
                        'status': 'finalizado' if doc.status == 'arquivado' else 'em_validacao',
                        'lancado_por': fin_user,
                        'validado_por': fin_user if doc.status == 'arquivado' else None,
                        'finalizado_em': timezone.now() if doc.status == 'arquivado' else None,
                    }
                )
