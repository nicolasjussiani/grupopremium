"""Classificação conservadora do acervo pelo texto, sem criar lançamentos.

O conteúdo é evidência documental, nunca instruções para executar ações.
Regras específicas precedem os comprovantes bancários genéricos.
"""
import re
import unicodedata


def normalizar(texto):
    texto = unicodedata.normalize('NFKD', texto or '')
    return re.sub(r'\s+', ' ', ''.join(c for c in texto if not unicodedata.combining(c)).upper()).strip()


# Identificadores de tipos documentais, não palavras soltas como "nome" ou "valor".
REGRAS = (
    ('rh', 'documento_trabalhista', 'documento_pessoal', 'Documento pessoal para cadastro',
     r'CARTEIRA DE (?:IDENTIDADE|TRABALHO)|REGISTRO\s*GERAL|REGISTRO CIVIL|CADASTRO DE PESSOAS FISICAS|TITULO (?:DE )?ELEITOR|TRIBUNAL SUPERIOR ELEITORAL|CERTIDAO DE (?:NASCIMENTO|CASAMENTO)|CERTIFICADO DE DISPENSA DE INCORPORACAO|NUMERO DE IDENTIFICACAO DO TRABALHADOR|PROGRAMA DE INTEGRACAO SOCIAL'),
    ('rh', 'documento_trabalhista', 'contrato_trabalho', 'Contrato de trabalho',
     r'CONTRATO (?:INDIVIDUAL )?DE TRABALHO|CONTRATO DE EXPERIENCIA|FICHA DE REGISTRO (?:DE |DO )?EMPREGADO'),
    ('rh', 'documento_trabalhista', 'rescisao', 'Rescisão ou quitação trabalhista',
     r'TERMO DE (?:RESCISAO|QUITACAO)|RESCISAO (?:DO |DE )?CONTRATO|VERBAS RESCISORIAS'),
    ('rh', 'pagamento_colaborador', 'salario', 'Folha ou recibo de salário',
     r'FOLHA DE PAGAMENTO|RECIBO DE (?:PAGAMENTO DE )?SALARIO|DEMONSTRATIVO DE PAGAMENTO|HOLERITE|TOTAL (?:DE )?PROVENTOS|SALARIO (?:BASE|LIQUIDO)'),
    ('rh', 'pagamento_colaborador', 'vale_transporte', 'Benefício de transporte',
     r'VALE[ -]?TRANSPORTE|AUXILIO[ -]?TRANSPORTE'),
    ('rh', 'documento_trabalhista', 'encargos', 'Encargos trabalhistas',
     r'GUIA (?:DE )?(?:RECOLHIMENTO (?:DO |DE )?)?(?:FGTS|PREVIDENCIA SOCIAL)|FGTS DIGITAL|FUNDO DE GARANTIA DO TEMPO DE SERVICO'),
    ('sesmet', 'documento_trabalhista', 'seguranca', 'Saúde e segurança do trabalho',
     r'ATESTADO DE SAUDE OCUPACIONAL|PROGRAMA DE CONTROLE MEDICO|FICHA DE (?:ENTREGA|CONTROLE) DE EPI|EQUIPAMENTO DE PROTECAO INDIVIDUAL|ORDEM DE SERVICO DE SEGURANCA|TREINAMENTO.{0,80}(?:NR[ -]?35|NR[ -]?10|NR[ -]?33)|RISCO QUIMICO.{0,400}EPIS'),
    ('recrutamento', 'outro', 'curriculo', 'Currículo profissional',
     r'CURRICULUM VITAE|CURRICULO (?:PROFISSIONAL|VITAE)|OBJETIVO PROFISSIONAL.{0,700}(?:EXPERIENCIA|FORMACAO)'),
    ('fiscal', 'nota_fiscal', 'nota_fiscal', 'Nota fiscal',
     r'NOTA FISCAL|DOCUMENTO AUXILIAR DA NOTA|\bDANFE\b|\bNFSE\b|\bNFS[ -]?E\b'),
    ('fiscal', 'documento_financeiro', 'tributos', 'Guia ou declaração tributária',
     r'DOCUMENTO DE ARRECADACAO|ARRECADACAO (?:DE )?RECEITAS FEDERAIS|DECLARACAO DE DEBITOS E CREDITOS TRIBUTARIOS'),
    ('compras', 'pedido', 'pedido', 'Pedido de compra ou cotação',
     r'PEDIDO DE COMPRA|ORDEM DE COMPRA|SOLICITACAO DE (?:MATERIAIS|COMPRA)|COTACAO DE (?:PRECOS|MATERIAIS)'),
    ('manutencao', 'outro', 'manutencao', 'Manutenção de equipamentos',
     r'MANUTENCAO (?:PREVENTIVA|CORRETIVA)|RELATORIO DE MANUTENCAO|ORDEM DE SERVICO.{0,80}(?:REPARO|EQUIPAMENTO|MAQUINA)'),
    ('administrativo', 'outro', 'contrato', 'Contrato de locação ou documento societário',
     r'CONTRATO DE LOCACAO|CONTRATO SOCIAL|ATA DE (?:REUNIAO|ASSEMBLEIA)'),
)


def classificar_texto(texto):
    normalizado = normalizar(texto)
    base = {'versao': 1, 'area': '', 'categoria': '', 'subcategoria': '',
            'resumo': '', 'evidencia': '', 'confianca': 'revisar'}
    if len(normalizado) < 40:
        return {**base, 'motivo': 'Texto insuficiente ou ilegível para identificar a área.'}
    encontrados = []
    for area, categoria, subcategoria, resumo, padrao in REGRAS:
        match = re.search(padrao, normalizado)
        if match:
            encontrados.append({**base, 'area': area, 'categoria': categoria, 'subcategoria': subcategoria,
                'resumo': resumo, 'evidencia': match.group(0)[:220], 'confianca': 'alta'})
    areas = {x['area'] for x in encontrados}
    if len(areas) > 1:
        return {**base, 'motivo': 'O conteúdo reúne sinais de mais de uma área; conferir antes de mover.',
                'evidencia': '; '.join(x['evidencia'] for x in encontrados)[:500]}
    if encontrados:
        return encontrados[0]
    pix = re.search(r'PIX.{0,45}REALIZADO', normalizado)
    if pix and re.search(r'BANCO|AGENCIA|AUTENTICACAO', normalizado):
        return {**base, 'area': 'financeiro', 'categoria': 'documento_financeiro',
                'subcategoria': 'comprovante', 'resumo': 'Comprovante bancário',
                'evidencia': pix.group(0), 'confianca': 'alta'}
    financeiros = (
        (r'COMPROVANTE (?:DE )?(?:PAGAMENTO|TRANSFERENCIA|PIX)|PIX (?:REALIZADO|ENVIADO|RECEBIDO)|TRANSFERENCIA (?:REALIZADA|EFETUADA)|PAGAMENTO EFETUADO', 'comprovante', 'Comprovante bancário'),
        (r'BOLETO (?:BANCARIO|DE COBRANCA)|FICHA DE COMPENSACAO|LINHA DIGITAVEL', 'boleto', 'Boleto bancário'),
        (r'RECIBO (?:DE )?PAG(?:AMENTO|TO)|RECIBO.{0,80}(?:VALOR|QUANTIA)|RECEBI.{0,100}(?:QUANTIA|IMPORTANCIA)', 'recibo', 'Recibo de pagamento'),
        (r'PRESTACAO DE CONTAS|RELATORIO DE DESPESAS|CONTAS A PAGAR|CONTAS A RECEBER|FLUXO DE CAIXA', 'controle_financeiro', 'Controle financeiro'),
        (r'EXTRATO (?:BANCARIO|DE CONTA)|SALDO ANTERIOR.{0,200}(?:DEBITO|CREDITO)', 'extrato', 'Extrato bancário'),
    )
    for padrao, subcategoria, resumo in financeiros:
        match = re.search(padrao, normalizado)
        if match:
            return {**base, 'area': 'financeiro', 'categoria': 'documento_financeiro',
                    'subcategoria': subcategoria, 'resumo': resumo, 'evidencia': match.group(0)[:220], 'confianca': 'alta'}
    return {**base, 'motivo': 'Texto lido, mas sem indicação suficiente de uma área responsável.'}


def classificar_documento(texto, nome=''):
    """Usa a finalidade explícita do nome apenas quando o conteúdo a corrobora."""
    resultado = classificar_texto(texto)
    conteudo, titulo = normalizar(texto), normalizar(nome)
    if len(conteudo) < 40:
        return resultado
    contextos = (
        (r'RESIDEN|ENDERECO', r'CONTA|FATURA|ENERGIA|AGUA|CEP|INSTALACAO|CPF', 'rh', 'documento_trabalhista', 'comprovante_residencia', 'Comprovante de residência para cadastro'),
        (r'\b(?:RG|CPF|CTPS|PIS|RESERVISTA)\b', r'REPUBLICA|FILIACAO|CPF|REGISTRO|IDENTIFICACAO|TRABALHADOR|MINISTERIO|CAIXA', 'rh', 'documento_trabalhista', 'documento_pessoal', 'Documento pessoal para cadastro'),
        (r'DADOS DE INFORMACAO PESSOAL', r'CPF.{0,300}(?:CEL|PIX|BANCO|CAMISA)', 'rh', 'documento_trabalhista', 'cadastro', 'Dados cadastrais do colaborador'),
        (r'\bASO\b|ORDEM.{0,15}SERVICO|EPI', r'MEDICO|APTO|RISCO|EPIS|PROTECAO', 'sesmet', 'documento_trabalhista', 'seguranca', 'Saúde e segurança do trabalho'),
    )
    for nome_regex, texto_regex, area, categoria, subcategoria, resumo in contextos:
        match = re.search(texto_regex, conteudo)
        if re.search(nome_regex, titulo) and match:
            return {**resultado, 'area': area, 'categoria': categoria, 'subcategoria': subcategoria,
                    'resumo': resumo, 'evidencia': f'Finalidade no nome: {nome[:100]}. Conteúdo identificado: {match.group(0)[:150]}.',
                    'confianca': 'alta', 'motivo': 'Finalidade explícita no nome, corroborada pela leitura do documento.'}
    return resultado


def aplicar_classificacao(arquivo, texto, *, metodo):
    """Prepara alterações apenas no acervo. O chamador persiste os campos.

Datas, valores, vínculos, observações e arquivos originais não são alterados.
"""
    resultado = classificar_documento(texto, arquivo.nome_original)
    resultado['metodo_leitura'] = metodo
    resultado['aplicada'] = False
    metadados = {**(arquivo.metadados or {})}
    if metadados.get('classificacao_manual'):
        resultado['motivo'] = 'Classificação manual preservada.'
    elif arquivo.object_id and resultado['area'] != arquivo.area:
        resultado['motivo'] = 'Área do vínculo existente preservada; confira a sugestão de leitura.'
    elif resultado['confianca'] == 'alta':
        arquivo.area = resultado['area']
        # Uma categoria de negócio já vinculada exige revisão no próprio fluxo.
        if not arquivo.object_id:
            arquivo.categoria = resultado['categoria']
            arquivo.subcategoria = resultado['subcategoria']
        resultado['aplicada'] = True
    if resultado['confianca'] != 'alta' and not arquivo.object_id:
        arquivo.status = 'revisar'
    arquivo.texto_extraido = texto or arquivo.texto_extraido
    metadados['classificacao_conteudo'] = resultado
    arquivo.metadados = metadados
    return resultado
