"""Fluxos resumidos exibidos nas telas principais do ERP."""


def _flow(title, description, theme, steps, branches=()):
    return {
        'title': title,
        'description': description,
        'theme': theme,
        'steps': [
            {'label': label, 'detail': detail}
            for label, detail in steps
        ],
        'branches': [
            {'condition': condition, 'result': result}
            for condition, result in branches
        ],
    }


FLOWS = {
    'cadastros': _flow(
        'Fornecedores e unidades',
        'Base compartilhada pelos módulos operacionais.',
        'core',
        (
            ('Cadastrar', 'Informe os dados principais.'),
            ('Validar', 'O sistema verifica códigos e duplicidades.'),
            ('Disponibilizar', 'O cadastro passa a alimentar os formulários.'),
            ('Atualizar', 'Dados e situação podem ser mantidos pela gestão.'),
        ),
    ),
    'auditoria': _flow(
        'Auditoria global',
        'Rastreabilidade das alterações realizadas no ERP.',
        'core',
        (
            ('Ação registrada', 'Uma operação de escrita é concluída.'),
            ('Identificação', 'Usuário, módulo, endereço e horário são gravados.'),
            ('Notificação', 'A área responsável recebe o aviso aplicável.'),
            ('Consulta', 'A diretoria filtra e revisa o histórico.'),
        ),
    ),
    'sla': _flow(
        'Tempo dos processos',
        'Acompanhamento da idade e do andamento dos registros.',
        'core',
        (
            ('Processo criado', 'O relógio começa no cadastro.'),
            ('Mudança de etapa', 'O status atual define o ponto do fluxo.'),
            ('Medição', 'O painel calcula o tempo em aberto.'),
            ('Priorização', 'Os registros mais antigos recebem atenção.'),
            ('Conclusão', 'O tempo final permanece no histórico.'),
        ),
    ),
    'usuarios': _flow(
        'Usuários e acessos',
        'Criação e manutenção das permissões do ERP.',
        'core',
        (
            ('Criar usuário', 'Defina identificação e credenciais.'),
            ('Escolher perfil', 'Associe a área de atuação.'),
            ('Aplicar grupos', 'Permissões específicas são vinculadas.'),
            ('Acessar módulos', 'O menu respeita perfil e permissões.'),
        ),
        (
            ('Sem permissão', 'Acesso negado e retorno ao painel'),
            ('Com permissão', 'Área liberada'),
        ),
    ),
    'recrutamento': _flow(
        'Recrutamento e seleção',
        'Da abertura da vaga ao encaminhamento para admissão.',
        'mod1',
        (
            ('Abrir vaga', 'Defina função, unidade, perfil e condições.'),
            ('Cadastrar candidato', 'Currículo e dados entram na triagem.'),
            ('Avaliar DP', 'Registre a avaliação comportamental.'),
            ('Entrevista final', 'O gestor registra o resultado.'),
            ('Encaminhar', 'O aprovado gera um processo admissional.'),
        ),
        (
            ('Reprovado', 'Retorna a vaga para nova seleção'),
            ('Aprovado', 'Vaga preenchida e admissão criada'),
        ),
    ),
    'talentos': _flow(
        'Banco de talentos',
        'Organização e reaproveitamento de candidatos.',
        'mod1',
        (
            ('Receber currículo', 'Cadastre dados e arquivo do candidato.'),
            ('Classificar', 'Consulte cidade, experiência e última vaga.'),
            ('Selecionar talento', 'Escolha o perfil adequado à oportunidade.'),
            ('Vincular à vaga', 'Crie a candidatura na vaga escolhida.'),
            ('Iniciar triagem', 'O candidato entra no fluxo de seleção.'),
        ),
    ),
    'admissional': _flow(
        'Admissão de colaboradores',
        'Conferência documental até a liberação para a unidade.',
        'mod2',
        (
            ('Aguardar documentos', 'O candidato envia os documentos exigidos.'),
            ('Analisar', 'RH aprova ou rejeita cada documento.'),
            ('Cadastrar', 'Os dados são registrados no sistema.'),
            ('Gerar contrato', 'O vínculo é formalizado.'),
            ('Integrar e entregar EPIs', 'Integração e segurança são concluídas.'),
            ('Liberar', 'O colaborador segue para a unidade.'),
        ),
        (
            ('Documento rejeitado', 'Solicitar correção e analisar novamente'),
            ('Tudo aprovado', 'Continuar para cadastro e contrato'),
        ),
    ),
    'administrativo': _flow(
        'Demandas administrativas',
        'Da solicitação ao encerramento da demanda.',
        'mod3',
        (
            ('Registrar demanda', 'Informe tipo, prioridade e necessidade.'),
            ('Triar', 'A área confere as informações.'),
            ('Executar', 'O responsável realiza a atividade.'),
            ('Revisar', 'O resultado é conferido.'),
            ('Arquivar', 'A demanda é marcada como concluída.'),
        ),
        (
            ('Informação incompleta', 'Retornar ao solicitante'),
            ('Necessita ajuste', 'Retornar para execução'),
        ),
    ),
    'sesmet': _flow(
        'SESMET e controle de EPIs',
        'Entrega, assinatura e renovação dos equipamentos.',
        'mod4',
        (
            ('Cadastrar EPI', 'Inclua CA, validade, foto e estoque.'),
            ('Entregar', 'A retirada reduz o estoque.'),
            ('Orientar', 'O colaborador acessa o treinamento.'),
            ('Assinar', 'A assinatura digital confirma o recebimento.'),
            ('Monitorar 90 dias', 'Alertas indicam proximidade do vencimento.'),
            ('Renovar ou devolver', 'O ciclo anterior é encerrado.'),
        ),
        (
            ('Estoque insuficiente', 'Entrega bloqueada'),
            ('EPI vencendo', 'Programar substituição'),
        ),
    ),
    'compras': _flow(
        'Compras e almoxarifado',
        'Solicitação, aprovação e atendimento dos materiais.',
        'mod5',
        (
            ('Criar requisição', 'Agrupe os produtos da mesma unidade.'),
            ('Aprovação inicial', 'Adriana analisa a necessidade.'),
            ('Aprovação final', 'O CEO decide a liberação.'),
            ('Verificar estoque', 'Cada item é analisado separadamente.'),
            ('Comprar ou separar', 'Atendimento interno ou pedido externo.'),
            ('Entregar', 'Recebimento e conclusão do pedido.'),
        ),
        (
            ('Há estoque', 'Baixar saldo e atender internamente'),
            ('Sem estoque', 'Cotação e compra externa'),
            ('Pedido rejeitado', 'Realizar nova cotação'),
        ),
    ),
    'financeiro': _flow(
        'Financeiro e fiscal',
        'Auditoria do documento até o lançamento definitivo.',
        'mod6',
        (
            ('Receber documento', 'Cadastre valores, emissor e arquivo.'),
            ('Extrair dados', 'OCR pode preencher os campos iniciais.'),
            ('Auditar', 'O checklist confere dados e itens.'),
            ('Lançar', 'Crie o registro contábil no ERP.'),
            ('Validar', 'O aprovador realiza a conferência final.'),
            ('Arquivar', 'O lançamento finalizado encerra o processo.'),
        ),
        (
            ('Auditoria divergente', 'Corrigir o documento'),
            ('Lançamento rejeitado', 'Corrigir e lançar novamente'),
        ),
    ),
    'pagamentos': _flow(
        'Folha de pagamento',
        'Controle dos pagamentos e benefícios dos colaboradores.',
        'mod6',
        (
            ('Selecionar colaborador', 'Consulte contrato, categoria e faltas.'),
            ('Cadastrar pagamento', 'Informe tipo, período e vencimento.'),
            ('Acompanhar pendência', 'O valor permanece no total em aberto.'),
            ('Confirmar pagamento', 'Registre data e comprovante.'),
            ('Consolidar', 'Totais e benefícios ficam disponíveis para consulta.'),
        ),
    ),
    'arquivo_central': _flow(
        'Arquivo Central',
        'Classificação e vínculo dos documentos importados.',
        'mod6',
        (
            ('Receber arquivo', 'O sistema identifica origem e hash.'),
            ('Classificar', 'Categoria e metadados são extraídos.'),
            ('Localizar vínculo', 'O sistema procura colaborador ou registro.'),
            ('Vincular', 'O documento passa ao processo correspondente.'),
            ('Revisar', 'Casos incertos aguardam correção manual.'),
        ),
        (
            ('Arquivo duplicado', 'Não importar novamente'),
            ('Correspondência incerta', 'Enviar para revisão'),
        ),
    ),
    'manutencao': _flow(
        'Manutenção e patrimônio',
        'Abertura do chamado até o retorno do ativo.',
        'mod3',
        (
            ('Selecionar ativo', 'Registre defeito, unidade e evidências.'),
            ('Solicitar aprovação', 'O ativo fica em manutenção.'),
            ('Analisar', 'O CEO aprova ou rejeita o chamado.'),
            ('Executar reparo', 'Registre fornecedor, custo e laudo.'),
            ('Concluir', 'Defina a unidade de retorno.'),
            ('Liberar ativo', 'O patrimônio volta ao status ativo.'),
        ),
        (
            ('Chamado rejeitado', 'Cancelar e liberar o ativo'),
            ('Chamado aprovado', 'Abrir manutenção'),
        ),
    ),
    'aprovacoes': _flow(
        'Central de aprovações',
        'Decisões pendentes e retorno ao módulo de origem.',
        'core',
        (
            ('Receber solicitação', 'O módulo cria uma aprovação pendente.'),
            ('Notificar responsável', 'A decisão aparece na web e no celular.'),
            ('Analisar detalhes', 'O aprovador consulta dados e anexos.'),
            ('Decidir', 'Aprovar ou rejeitar com motivo.'),
            ('Atualizar processo', 'O módulo de origem recebe o resultado.'),
            ('Registrar histórico', 'A decisão permanece na auditoria.'),
        ),
        (
            ('Compras', 'Adriana primeiro e CEO depois'),
            ('Rejeição', 'Motivo obrigatório e retorno ao solicitante'),
        ),
    ),
    'colaboradores': _flow(
        'Gestão de colaboradores',
        'Cadastro, documentação e situação funcional.',
        'mod2',
        (
            ('Cadastrar', 'Informe dados pessoais e profissionais.'),
            ('Completar documentos', 'Anexe comprovantes e contratos.'),
            ('Acompanhar', 'Consulte contrato, unidade e situação.'),
            ('Atualizar status', 'Ativo, férias, afastado ou inativo.'),
            ('Desligar ou reativar', 'O histórico é preservado.'),
        ),
        (
            ('Documentação incompleta', 'Exibir pendência'),
            ('Documentação completa', 'Cadastro regular'),
        ),
    ),
    'presenca': _flow(
        'Controle de presença',
        'Registro diário usado nos acompanhamentos do colaborador.',
        'mod2',
        (
            ('Escolher data', 'Abra o controle do dia.'),
            ('Selecionar unidade', 'Filtre os colaboradores aplicáveis.'),
            ('Registrar situação', 'Presente, falta, atestado ou folga.'),
            ('Salvar', 'Uma situação por colaborador e data.'),
            ('Consolidar', 'Faltas alimentam os resumos de pagamento.'),
        ),
    ),
    'experiencia': _flow(
        'Período de experiência',
        'Acompanhamento dos marcos iniciais do vínculo.',
        'mod2',
        (
            ('Admissão registrada', 'A data inicial define os prazos.'),
            ('Primeiro período', 'O sistema acompanha o marco inicial.'),
            ('Revisão', 'RH verifica a continuidade do colaborador.'),
            ('Segundo período', 'O prazo final permanece monitorado.'),
            ('Efetivação', 'O acompanhamento de experiência é encerrado.'),
        ),
    ),
}


ROUTE_FLOW_KEYS = {
    'cadastros_gerais': 'cadastros',
    'auditoria_sistema': 'auditoria',
    'painel_sla': 'sla',
    'lista_usuarios': 'usuarios',
    'lista_vagas': 'recrutamento',
    'banco_talentos': 'talentos',
    'lista_admissoes': 'admissional',
    'lista_demandas': 'administrativo',
    'dashboard_sesmet': 'sesmet',
    'catalogo_equipamentos': 'sesmet',
    'painel_compras': 'compras',
    'painel_financeiro': 'financeiro',
    'lista_pagamentos_colaboradores': 'pagamentos',
    'arquivo_central': 'arquivo_central',
    'painel_manutencao': 'manutencao',
    'aprovacoes_pendentes': 'aprovacoes',
    'painel_mobile': 'aprovacoes',
    'lista_colaboradores': 'colaboradores',
    'controle_presenca': 'presenca',
    'periodo_experiencia': 'experiencia',
}


def flow_for_request(request):
    match = getattr(request, 'resolver_match', None)
    route_name = getattr(match, 'url_name', None)
    return FLOWS.get(ROUTE_FLOW_KEYS.get(route_name))
