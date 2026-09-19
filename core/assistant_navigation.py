"""Catálogo de processos usado pela assistente para orientar e navegar no ERP."""

from django.urls import reverse

from core.access import user_has_access, user_is_executive


PROCESS_CATALOG = (
    {
        'key': 'colaborador',
        'title': 'Cadastrar colaborador',
        'summary': 'Cadastre dados pessoais, vínculo, salário mensal e benefício semanal.',
        'directory': 'Admissional > Colaboradores > Novo colaborador',
        'route': 'novo_colaborador',
        'keywords': ('colaborador', 'admissao', 'admissional', 'salario', 'vale transporte', 'ajuda de custo'),
        'profiles': ('admin', 'rh', 'gestor'),
        'groups': ('Admissional_RH',),
        'permission': 'admissional.add_colaborador',
        'theme': 'green',
    },
    {
        'key': 'folha',
        'title': 'Folha e pagamentos',
        'summary': 'Consulte lançamentos, registre pagamentos e confirme quando forem efetivamente pagos.',
        'directory': 'Admissional > Colaboradores > Pagamentos',
        'route': 'lista_pagamentos_colaboradores',
        'keywords': ('folha', 'pagamento', 'pagar', 'beneficio', 'vt', 'vale transporte', 'ajuda de custo'),
        'profiles': ('admin', 'rh', 'financeiro', 'gestor'),
        'groups': ('Admissional_RH', 'Financeiro_Operador', 'Financeiro_Auditor'),
        'permission': 'admissional.view_pagamentocolaborador',
        'theme': 'yellow',
    },
    {
        'key': 'fiscal',
        'title': 'Importar base Fiscal',
        'summary': 'Importe a planilha, concilie colaboradores, revise divergências e gere pagamentos.',
        'directory': 'Financeiro > Base Fiscal',
        'route': 'painel_fiscal',
        'keywords': ('fiscal', 'planilha', 'importar folha', 'base fiscal'),
        'profiles': ('admin', 'financeiro', 'gestor'),
        'groups': ('Financeiro_Operador', 'Financeiro_Auditor', 'Financeiro_Aprovador'),
        'permission': 'fiscal.view_folhafiscal',
        'theme': 'yellow',
    },
    {
        'key': 'recrutamento',
        'title': 'Abrir vaga e selecionar',
        'summary': 'Abra uma vaga, cadastre candidatos, faça a triagem e encaminhe o aprovado à admissão.',
        'directory': 'Recrutamento > Vagas > Nova vaga',
        'route': 'nova_vaga',
        'keywords': ('vaga', 'candidato', 'recrutamento', 'contratar'),
        'profiles': ('admin', 'rh', 'gestor'),
        'groups': ('Recrutamento_RH',),
        'permission': 'recrutamento.add_vaga',
        'theme': 'blue',
    },
    {
        'key': 'presenca',
        'title': 'Registrar presença',
        'summary': 'Escolha a data e informe presença, falta, atestado ou folga de cada colaborador.',
        'directory': 'Admissional > Controle de presença',
        'route': 'controle_presenca',
        'keywords': ('presenca', 'falta', 'atestado', 'folga'),
        'profiles': ('admin', 'rh', 'gestor'),
        'groups': ('Admissional_RH',),
        'permission': 'admissional.change_presencadiaria',
        'theme': 'green',
    },
    {
        'key': 'epi',
        'title': 'Entregar e controlar EPI',
        'summary': 'Registre a entrega, recolha a assinatura e acompanhe o ciclo de renovação.',
        'directory': 'SESMET > Registrar entrega de EPI',
        'route': 'registrar_epi',
        'keywords': ('epi', 'equipamento', 'seguranca', 'sesmet'),
        'profiles': ('admin', 'sesmet', 'gestor', 'estoque_compras'),
        'groups': ('Estoque_EPI_Compras',),
        'permission': 'sesmet.add_registroepi',
        'theme': 'cyan',
    },
    {
        'key': 'compras',
        'title': 'Solicitar material ou compra',
        'summary': 'Crie a requisição, aguarde as aprovações e acompanhe separação ou compra externa.',
        'directory': 'Compras > Nova solicitação',
        'route': 'nova_solicitacao',
        'keywords': ('compra', 'material', 'pedido', 'requisicao', 'estoque'),
        'profiles': ('admin', 'compras', 'gestor', 'estoque_compras'),
        'groups': ('Estoque_EPI_Compras',),
        'permission': 'compras.add_solicitacaomaterial',
        'theme': 'purple',
    },
    {
        'key': 'financeiro',
        'title': 'Lançar documento financeiro',
        'summary': 'Cadastre o documento, faça a auditoria, lance no ERP e envie para validação final.',
        'directory': 'Financeiro > Novo documento',
        'route': 'entrada_documento',
        'keywords': ('nota fiscal', 'documento financeiro', 'lancamento', 'financeiro', 'ocr'),
        'profiles': ('admin', 'financeiro', 'gestor'),
        'groups': ('Financeiro_Operador', 'Financeiro_Auditor', 'Financeiro_Aprovador'),
        'permission': 'financeiro.add_documentofinanceiro',
        'theme': 'yellow',
    },
    {
        'key': 'aprovacoes',
        'title': 'Analisar aprovações',
        'summary': 'Consulte os detalhes e aprove ou rejeite somente os processos destinados a você.',
        'directory': 'Diretoria > Central de decisões',
        'route': 'aprovacoes_pendentes',
        'keywords': ('aprovar', 'aprovacao', 'decisao', 'pendencia'),
        'profiles': ('admin', 'gestor'),
        'groups': ('Admin_Global', 'Diretoria_Final', 'Intermediario_Gestor'),
        'permission': 'core.view_aprovacaoregistro',
        'theme': 'navy',
    },
    {
        'key': 'manutencao',
        'title': 'Abrir manutenção',
        'summary': 'Selecione o ativo, registre o defeito e acompanhe aprovação, reparo e devolução.',
        'directory': 'Manutenção > Nova manutenção',
        'route': 'nova_manutencao',
        'keywords': ('manutencao', 'ativo', 'patrimonio', 'defeito', 'reparo'),
        'profiles': ('admin', 'sesmet', 'gestor', 'compras', 'rh'),
        'groups': (),
        'permission': 'manutencao.add_registromanutencao',
        'theme': 'orange',
    },
)


def processes_for_user(user):
    """Retorna apenas atalhos que o usuário pode efetivamente abrir."""
    items = []
    for process in PROCESS_CATALOG:
        if user_is_executive(user) or user_has_access(
            user,
            permission=process['permission'],
            profiles=process['profiles'],
            groups=process['groups'],
        ):
            item = dict(process)
            item['url'] = reverse(process['route'])
            items.append(item)
    return items


def recommend_process(user, question):
    normalized = ' '.join((question or '').casefold().split())
    ranked = []
    for item in processes_for_user(user):
        score = sum(1 for keyword in item['keywords'] if keyword in normalized)
        if score:
            ranked.append((score, item))
    return max(ranked, key=lambda result: result[0])[1] if ranked else None


def answer_with_process(user, question, fallback):
    """Prioriza orientação operacional quando a pergunta pede como/onde fazer."""
    process = recommend_process(user, question)
    normalized = ' '.join((question or '').casefold().split())
    asks_for_guidance = any(
        term in normalized
        for term in ('como ', 'onde ', 'quero ', 'preciso ', 'qual tela', 'qual caminho')
    )
    if process and asks_for_guidance:
        return (
            f'{process["summary"]} Para começar, siga o caminho '
            f'{process["directory"]} e use o botão “Abrir tela indicada”.'
        )
    return fallback
