import hashlib
import mimetypes
import re
import unicodedata
import zipfile
from calendar import monthrange
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree

from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from admissional.models import Colaborador, PagamentoColaborador
from core.models import ArquivoImportado, OrigemArquivoImportado


EXTENSOES_SUPORTADAS = {'.pdf', '.xml', '.docx', '.xlsx', '.jpg', '.jpeg', '.png'}
PALAVRAS_NOME = {'DA', 'DAS', 'DE', 'DO', 'DOS', 'E'}


def normalizar(valor):
    valor = unicodedata.normalize('NFKD', str(valor or ''))
    valor = ''.join(char for char in valor if not unicodedata.combining(char))
    return re.sub(r'[^A-Z0-9]+', ' ', valor.upper()).strip()


def sha256_arquivo(caminho):
    digest = hashlib.sha256()
    with caminho.open('rb') as stream:
        for bloco in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(bloco)
    return digest.hexdigest()


def nome_seguro_storage(nome):
    """Gera uma chave ASCII compatível com o endpoint S3 do Supabase."""
    sem_acentos = unicodedata.normalize('NFKD', str(nome or ''))
    sem_acentos = sem_acentos.encode('ascii', 'ignore').decode('ascii')
    return get_valid_filename(sem_acentos)[:180]


def classificar(caminho_relativo):
    texto = normalizar(str(caminho_relativo))
    texto_nome = normalizar(caminho_relativo.name)
    partes = caminho_relativo.parts
    topo = normalizar(partes[0]) if partes else ''

    subcategoria = ''
    if topo == 'AUXILIO TELEFONIA':
        categoria, subcategoria = 'pagamento_colaborador', 'auxilio_telefonia'
    elif topo.startswith('COMPROVANTES PARA LANCAMENTO'):
        if (
            re.search(r'\bNF\b|NOTA FISCAL', texto_nome)
            or re.search(r'\bPREMIUMBR\s+\d+', texto_nome)
        ):
            categoria, subcategoria = 'nota_fiscal', 'nota_fiscal'
        elif 'GUIA DE FGTS' in texto_nome:
            categoria, subcategoria = 'documento_trabalhista', 'fgts'
        elif 'TERMO DE RESCISAO' in texto_nome:
            categoria, subcategoria = 'documento_trabalhista', 'rescisao'
        elif 'BOLETO' in texto_nome:
            categoria, subcategoria = 'documento_financeiro', 'boleto'
        else:
            categoria, subcategoria = 'documento_financeiro', 'comprovante'
    elif topo in {'AGOSTO', 'SETEMBRO'} or topo.startswith('COMPROVANTE PAGAMENTO') or topo.startswith('COMPROVANTE SALARIO') or topo.startswith('COMPROVANTE VT'):
        categoria = 'pagamento_colaborador'
    elif 'REEMBOLSO' in topo:
        categoria = 'reembolso'
    elif topo == 'NOTAS FISCAIS':
        categoria = 'nota_fiscal'
    else:
        categoria = 'outro'

    if subcategoria:
        pass
    elif 'REEMBOLSO' in texto_nome or categoria == 'reembolso':
        subcategoria = 'reembolso'
    elif 'SALARIO E VT' in texto_nome or 'SALARIO E BENEFICIO' in texto_nome:
        subcategoria = 'salario_beneficios'
    elif 'AJUDA DE CUSTO' in texto_nome:
        subcategoria = 'ajuda_custo'
    elif 'ADIANTAMENTO' in texto_nome:
        subcategoria = 'adiantamento'
    elif 'VALE TRANSPORTE' in texto_nome or re.search(r'\bVT\b', texto_nome):
        subcategoria = 'vale_transporte'
    elif 'FREELANC' in texto_nome:
        subcategoria = 'freelancer'
    elif 'DISTRATO' in texto_nome:
        subcategoria = 'distrato'
    elif 'SERVICOS PRESTADOS' in texto_nome or 'PRESTACAO DE SERVICO' in texto_nome:
        subcategoria = 'prestacao_servico'
    elif 'SALARIO' in texto_nome or topo == 'SETEMBRO':
        subcategoria = 'salario'
    elif 'PEDIDO' in texto:
        categoria, subcategoria = 'pedido', 'pedido'
    elif caminho_relativo.suffix.lower() == '.xlsx':
        categoria, subcategoria = 'planilha', 'planilha'
    elif categoria == 'nota_fiscal':
        subcategoria = 'nota_fiscal'
    else:
        subcategoria = 'outro'
    return categoria, subcategoria


def area_responsavel(categoria, subcategoria=''):
    if categoria in {'pagamento_colaborador', 'documento_trabalhista'}:
        return 'rh'
    if categoria in {'documento_financeiro', 'reembolso'}:
        return 'financeiro'
    if categoria in {'nota_fiscal', 'planilha'}:
        return 'fiscal'
    if categoria == 'pedido':
        return 'compras'
    return 'geral'


def classificar_pagamento_regra(subcategoria, data_pagamento, valor, colaborador=None):
    """Aplica as regras de negócio sobre a classificação extraída do arquivo."""
    tipos_preservados = {
        'freelancer', 'distrato', 'reembolso', 'prestacao_servico',
        'auxilio_telefonia',
    }
    if subcategoria in tipos_preservados:
        return subcategoria
    if data_pagamento and valor is not None:
        if 4 <= data_pagamento.day <= 15 and valor > Decimal('1000'):
            return 'salario'
        if data_pagamento.weekday() == 0 and (
            valor < Decimal('200')
            or (colaborador and colaborador.tipo_contrato == 'pj')
        ):
            return (
                'ajuda_custo'
                if colaborador and colaborador.tipo_contrato == 'pj'
                else 'vale_transporte'
            )
    if subcategoria == 'adiantamento':
        return (
            'prestacao_servico'
            if colaborador and colaborador.tipo_contrato == 'pj'
            else 'adiantamento'
        )
    if subcategoria == 'vale_transporte' and colaborador and colaborador.tipo_contrato == 'pj':
        return 'ajuda_custo'
    if subcategoria == 'ajuda_custo' and colaborador and colaborador.tipo_contrato == 'clt':
        return 'vale_transporte'
    return subcategoria


def extrair_texto(caminho, categoria):
    extensao = caminho.suffix.lower()
    if extensao == '.pdf':
        try:
            import pymupdf
            with pymupdf.open(caminho) as documento:
                return '\n'.join(pagina.get_text() for pagina in documento)[:40000]
        except Exception:
            return ''
    if extensao == '.docx' and categoria in {'pagamento_colaborador', 'reembolso'}:
        try:
            with zipfile.ZipFile(caminho) as documento:
                xml = documento.read('word/document.xml')
            raiz = ElementTree.fromstring(xml)
            return '\n'.join(
                elemento.text or '' for elemento in raiz.iter()
                if elemento.tag.rsplit('}', 1)[-1] == 't'
            )[:40000]
        except Exception:
            return ''
    return ''


def _primeiro_grupo(padroes, texto):
    for padrao in padroes:
        encontrado = re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)
        if encontrado:
            return encontrado.group(1).strip()
    return ''


def extrair_valor(texto):
    valor = _primeiro_grupo([
        r'Valor da transfer[eê]ncia\s*R\$\s*([\d.]+,\d{2})',
        r'Valor do documento\s*R\$\s*([\d.]+,\d{2})',
        r'(?:Valor|Quantia)\s*R\$\s*([\d.]+,\d{2})',
        r'R\$\s*([\d.]+,\d{2})',
    ], texto)
    if not valor:
        return None
    try:
        return Decimal(valor.replace('.', '').replace(',', '.'))
    except InvalidOperation:
        return None


def _converter_data(valor):
    if not valor:
        return None
    for formato in ('%d/%m/%Y', '%d.%m.%Y', '%d.%m.%y', '%d-%m-%Y', '%d-%m-%y'):
        try:
            data = datetime.strptime(valor, formato).date()
            if data.year < 2000:
                data = data.replace(year=data.year + 2000)
            return data
        except ValueError:
            continue
    return None


def extrair_data(texto, nome):
    valor = _primeiro_grupo([
        r'Data da transfer[eê]ncia\s*(\d{2}/\d{2}/\d{4})',
        r'Data e hora da transa[cç][aã]o\s*(\d{2}/\d{2}/\d{4})',
        r'(?m)^\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*\d{2}:\d{2}',
        r'(?m)^\s*(\d{2}/\d{2}/\d{4})\b',
    ], texto)
    data = _converter_data(valor)
    if data:
        return data
    iso = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', nome)
    if iso:
        try:
            return datetime.strptime(iso.group(1), '%Y-%m-%d').date()
        except ValueError:
            pass
    encontrado = re.search(r'(\d{2}[.\-]\d{2}[.\-](?:\d{2}|\d{4}))', nome)
    return _converter_data(encontrado.group(1)) if encontrado else None


def extrair_beneficiario(texto):
    return _primeiro_grupo([
        r'Dados de quem est[aá] recebendo\s+Nome\s+([^\r\n]+)',
        r'Benefici[aá]rio final\s+([^\r\n]+)',
        r'Nome do favorecido\s+([^\r\n]+)',
        r'Favorecido\s+([^\r\n]+)',
    ], texto)


def extrair_nome_trabalhador(texto):
    return _primeiro_grupo([
        r'IDENTIFICA[CÇC][AÃA]O DO TRABALHADOR.*?\b11 Nome\s+([^\r\n]+)',
        r'\b11 Nome\s+([^\r\n]+)',
    ], texto)


def extrair_identificador(texto):
    return _primeiro_grupo([
        r'ID da transa[cç][aã]o\s+([A-Za-z0-9]+)',
        r'Autentica[cç][aã]o no comprovante\s+([A-Za-z0-9]+)',
        r'C[oó]digo de Autentica[cç][aã]o\s+([A-Za-z0-9]+)',
    ], texto)


def nome_indicado(caminho_relativo, subcategoria):
    partes = caminho_relativo.parts
    if len(partes) >= 3 and normalizar(partes[0]).startswith('COMPROVANTE VT'):
        return partes[-2]
    nome = caminho_relativo.stem
    nome = re.sub(r'\s*-\s*\d{2}[.\-]\d{2}[.\-]\d{2,4}.*$', '', nome)
    nome = re.sub(r'\s*-\s*\d+\s+DI[ÁA]RIAS.*$', '', nome, flags=re.IGNORECASE)
    prefixos = [
        r'^COMPROVANTE\s+', r'^PAGAMENTO\s+', r'^SAL[ÁA]RIO E VT SEMANAL\s*-\s*',
        r'^SERVI[ÇC]OS PRESTADOS\s*-\s*', r'^PRESTA[ÇC][ÃA]O DE SERVI[ÇC]O\s*(?:E ADIANTAMENTO)?\s*-\s*',
        r'^FREELANCER\s*-\s*', r'^ADIANTAMENTO\s*-?\s*',
        r'^VALE TRANSPORTE SEMANAL\s*-\s*',
    ]
    for prefixo in prefixos:
        nome = re.sub(prefixo, '', nome, flags=re.IGNORECASE)
    for sufixo in ('DISTRATO', 'FREELANCER'):
        nome = re.sub(rf'\s*-\s*{sufixo}.*$', '', nome, flags=re.IGNORECASE)
    return nome.strip(' -_')


def _pontuacao_nome(origem, destino):
    origem_n = normalizar(origem)
    destino_n = normalizar(destino)
    if not origem_n or not destino_n:
        return 0
    if origem_n == destino_n:
        return 1
    tokens_origem = {t for t in origem_n.split() if t not in PALAVRAS_NOME}
    tokens_destino = {t for t in destino_n.split() if t not in PALAVRAS_NOME}
    cobertura = len(tokens_origem & tokens_destino) / max(1, min(len(tokens_origem), len(tokens_destino)))
    sequencia = SequenceMatcher(None, origem_n, destino_n).ratio()
    return max(sequencia, cobertura * .78 + sequencia * .22)


def localizar_colaborador(nome, colaboradores, unidade=''):
    if not nome:
        return None, 0, False
    resultados = []
    unidade_n = normalizar(unidade)
    for colaborador in colaboradores:
        pontos = _pontuacao_nome(nome, colaborador.nome)
        if unidade_n and normalizar(colaborador.unidade) in unidade_n:
            pontos += .03
        if colaborador.status == 'ativo':
            pontos += .015
        resultados.append((min(pontos, 1), colaborador))
    resultados.sort(key=lambda item: (item[0], item[1].status == 'ativo'), reverse=True)
    if not resultados:
        return None, 0, False
    melhor_ponto, melhor = resultados[0]
    segundo_ponto = resultados[1][0] if len(resultados) > 1 else 0
    confiavel = melhor_ponto >= .80 and (melhor_ponto - segundo_ponto >= .045 or melhor_ponto >= .98)
    return melhor if confiavel else None, melhor_ponto, confiavel


def extrair_metadados_xml(caminho):
    try:
        raiz = ElementTree.parse(caminho).getroot()
    except (ElementTree.ParseError, OSError):
        return {}
    elementos = {}
    for elemento in raiz.iter():
        chave = elemento.tag.rsplit('}', 1)[-1]
        if elemento.text and elemento.text.strip() and chave not in elementos:
            elementos[chave] = elemento.text.strip()
    return {
        chave: elementos[chave]
        for chave in ('nNF', 'Numero', 'xNome', 'RazaoSocial', 'CNPJ', 'vNF', 'ValorServicos', 'dhEmi', 'dEmi', 'DataEmissao')
        if chave in elementos
    }


def analisar_arquivo(caminho, relativo, colaboradores):
    categoria, subcategoria = classificar(relativo)
    texto = extrair_texto(caminho, categoria)
    beneficiario = extrair_beneficiario(texto)
    if not beneficiario and categoria == 'documento_trabalhista':
        beneficiario = extrair_nome_trabalhador(texto)
    nome_arquivo = nome_indicado(relativo, subcategoria)
    unidade = relativo.parts[1] if len(relativo.parts) > 2 else ''
    valor = extrair_valor(texto)
    data_pagamento = extrair_data(texto, caminho.name)
    identificador = extrair_identificador(texto)
    metadados = {
        'beneficiario': beneficiario,
        'nome_indicado': nome_arquivo,
        'unidade_origem': unidade,
        'valor': f'{valor:.2f}'.replace('.', ',') if valor is not None else '',
        'data_pagamento': data_pagamento.isoformat() if data_pagamento else '',
        'identificador_transacao': identificador,
    }
    if caminho.suffix.lower() == '.xml':
        metadados.update(extrair_metadados_xml(caminho))

    match_beneficiario = localizar_colaborador(beneficiario, colaboradores, unidade)
    match_indicado = localizar_colaborador(nome_arquivo, colaboradores, unidade)
    colaborador = match_beneficiario[0] or match_indicado[0]
    motivos = []
    if match_beneficiario[0] and match_indicado[0] and match_beneficiario[0].pk != match_indicado[0].pk:
        if _pontuacao_nome(match_beneficiario[0].nome, match_indicado[0].nome) >= .94:
            colaborador = match_beneficiario[0]
        else:
            motivos.append(
                f'Beneficiário ({match_beneficiario[0].nome}) difere do nome do arquivo ({match_indicado[0].nome}).'
            )
            colaborador = None
    metadados['colaborador_sugerido_id'] = colaborador.pk if colaborador else None
    metadados['pontuacao_beneficiario'] = round(match_beneficiario[1], 3)
    metadados['pontuacao_nome_indicado'] = round(match_indicado[1], 3)

    subcategoria = classificar_pagamento_regra(
        subcategoria, data_pagamento, valor, colaborador
    )

    if categoria in {'pagamento_colaborador', 'reembolso'}:
        if subcategoria not in dict(PagamentoColaborador.TIPOS):
            motivos.append('Tipo do pagamento não identificado.')
        if not valor:
            motivos.append('Valor não identificado.')
        if not data_pagamento:
            motivos.append('Data do pagamento não identificada.')
        if not colaborador:
            motivos.append('Colaborador não identificado com segurança.')
    elif categoria == 'documento_financeiro':
        nome_generico = re.fullmatch(
            r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
            caminho.stem,
            flags=re.IGNORECASE,
        )
        if nome_generico or caminho.name.lower().startswith('whatsapp image'):
            motivos.append(
                'Comprovante financeiro com nome genérico; revise a natureza e o vínculo.'
            )
        elif not texto and caminho.suffix.lower() == '.pdf':
            motivos.append('Documento sem texto extraível; revise a classificação.')

    metadados = {chave: valor_meta for chave, valor_meta in metadados.items() if valor_meta not in ('', None)}
    return {
        'categoria': categoria,
        'subcategoria': subcategoria,
        'area': area_responsavel(categoria, subcategoria),
        'metadados': metadados,
        'colaborador': colaborador,
        'valor': valor,
        'data_pagamento': data_pagamento,
        'identificador': identificador,
        'motivos': list(dict.fromkeys(motivos)),
    }


class ImportadorArquivoCentral:
    def __init__(self, raiz, *, usuario=None, dry_run=False, progresso=None):
        self.raiz = Path(raiz).resolve()
        self.usuario = usuario
        self.dry_run = dry_run
        self.progresso = progresso or (lambda mensagem: None)
        # O acervo também contém comprovantes históricos e verbas pagas
        # depois do desligamento. Por isso, colaboradores inativos/desligados
        # continuam elegíveis para conciliação documental.
        self.colaboradores = list(Colaborador.objects.all())
        self._hashes_dry_run = set()
        self._arquivos_por_hash = dict(
            ArquivoImportado.objects.values_list('sha256', 'pk')
        )
        self._caminhos_origem = set(
            OrigemArquivoImportado.objects.values_list(
                'caminho_relativo', flat=True
            )
        )
        self.contadores = {
            'encontrados': 0,
            'novos': 0,
            'duplicados': 0,
            'origens_novas': 0,
            'pagamentos_criados': 0,
            'pagamentos_existentes': 0,
            'revisar': 0,
            'ignorados': 0,
            'erros': 0,
            'por_categoria': {},
            'por_subcategoria': {},
            'por_area': {},
            'motivos_revisao': {},
        }

    def executar(self, limite=None):
        arquivos = sorted(
            caminho for caminho in self.raiz.rglob('*')
            if caminho.is_file()
            and caminho.suffix.lower() in EXTENSOES_SUPORTADAS
            and not caminho.name.startswith('~$')
        )
        if limite:
            arquivos = arquivos[:limite]
        self.contadores['encontrados'] = len(arquivos)
        for indice, caminho in enumerate(arquivos, 1):
            close_old_connections()
            try:
                self._importar(caminho)
            except Exception as exc:
                # Uma conexao derrubada pelo pool nao deve inutilizar todo o
                # restante do lote. O arquivo com falha fica para a proxima
                # execucao idempotente e o proximo usa uma nova conexao.
                close_old_connections()
                self.contadores['erros'] += 1
                self.progresso(f'ERRO {caminho}: {exc}')
            if indice % 50 == 0:
                self.progresso(f'{indice}/{len(arquivos)} arquivos processados')
        return self.contadores

    def _importar(self, caminho):
        relativo = caminho.relative_to(self.raiz)
        digest = sha256_arquivo(caminho)
        existente_id = self._arquivos_por_hash.get(digest)
        if existente_id:
            self.contadores['duplicados'] += 1
            if self.dry_run:
                return
            caminho_relativo = str(relativo)
            if caminho_relativo not in self._caminhos_origem:
                _, criada = OrigemArquivoImportado.objects.get_or_create(
                    caminho_relativo=caminho_relativo,
                    defaults={
                        'arquivo_importado_id': existente_id,
                        'pasta_raiz': self.raiz.name,
                        'modificado_em': datetime.fromtimestamp(
                            caminho.stat().st_mtime, tz=timezone.get_current_timezone()
                        ),
                    },
                )
                self.contadores['origens_novas'] += int(criada)
                self._caminhos_origem.add(caminho_relativo)
            return
        if self.dry_run:
            if digest in self._hashes_dry_run:
                self.contadores['duplicados'] += 1
                return
            self._hashes_dry_run.add(digest)
            analise = analisar_arquivo(caminho, relativo, self.colaboradores)
            self._contabilizar_analise(analise)
            self.contadores['novos'] += 1
            if analise['motivos']:
                self.contadores['revisar'] += 1
            elif analise['categoria'] in {'pagamento_colaborador', 'reembolso'}:
                self.contadores['pagamentos_criados'] += 1
            return
        analise = analisar_arquivo(caminho, relativo, self.colaboradores)
        self._contabilizar_analise(analise)

        nome_seguro = nome_seguro_storage(caminho.name) or f'arquivo{caminho.suffix.lower()}'
        chave = f'arquivo_central/{digest[:2]}/{digest}-{nome_seguro}'
        # A chave ja e unica pelo SHA-256 e a tabela impede o mesmo conteudo
        # de ser cadastrado duas vezes. Salvar diretamente evita uma chamada
        # HEAD adicional por arquivo, que e instavel no endpoint S3 do
        # Supabase durante importacoes em lote.
        with caminho.open('rb') as stream:
            nome_armazenado = default_storage._save(
                chave, File(stream, name=nome_seguro)
            )

        try:
            with transaction.atomic():
                status = 'revisar' if analise['motivos'] else 'arquivado'
                arquivo = ArquivoImportado.objects.create(
                    categoria=analise['categoria'],
                    subcategoria=analise['subcategoria'],
                    area=analise['area'],
                    nome_original=caminho.name[:255],
                    arquivo=nome_armazenado,
                    sha256=digest,
                    tamanho=caminho.stat().st_size,
                    mime_type=mimetypes.guess_type(caminho.name)[0] or 'application/octet-stream',
                    status=status,
                    motivo_revisao=' '.join(analise['motivos']),
                    metadados=analise['metadados'],
                    importado_por=self.usuario,
                )
                OrigemArquivoImportado.objects.create(
                    arquivo_importado=arquivo,
                    caminho_relativo=str(relativo),
                    pasta_raiz=self.raiz.name,
                    modificado_em=datetime.fromtimestamp(
                        caminho.stat().st_mtime, tz=timezone.get_current_timezone()
                    ),
                )
                self.contadores['origens_novas'] += 1
                self._vincular_pagamento(arquivo, analise)
                self._vincular_documento_trabalhista(arquivo, analise)
        except IntegrityError:
            # O pool pode entregar uma leitura ligeiramente atrasada enquanto
            # outra retomada acabou de inserir o mesmo hash. A restricao unica
            # e a autoridade final: reutilize o registro vencedor e prossiga.
            close_old_connections()
            arquivo = ArquivoImportado.objects.get(sha256=digest)
            caminho_relativo = str(relativo)
            _, criada = OrigemArquivoImportado.objects.get_or_create(
                caminho_relativo=caminho_relativo,
                defaults={
                    'arquivo_importado': arquivo,
                    'pasta_raiz': self.raiz.name,
                    'modificado_em': datetime.fromtimestamp(
                        caminho.stat().st_mtime,
                        tz=timezone.get_current_timezone(),
                    ),
                },
            )
            self._arquivos_por_hash[digest] = arquivo.pk
            self._caminhos_origem.add(caminho_relativo)
            self.contadores['duplicados'] += 1
            self.contadores['origens_novas'] += int(criada)
            return
        self._arquivos_por_hash[digest] = arquivo.pk
        self._caminhos_origem.add(str(relativo))
        self.contadores['novos'] += 1
        if arquivo.status == 'revisar':
            self.contadores['revisar'] += 1

    def _contabilizar_analise(self, analise):
        categoria = analise['categoria']
        subcategoria = analise['subcategoria']
        categorias = self.contadores['por_categoria']
        subcategorias = self.contadores['por_subcategoria']
        areas = self.contadores['por_area']
        categorias[categoria] = categorias.get(categoria, 0) + 1
        subcategorias[subcategoria] = subcategorias.get(subcategoria, 0) + 1
        area = analise['area']
        areas[area] = areas.get(area, 0) + 1
        motivos = self.contadores['motivos_revisao']
        for motivo in analise['motivos']:
            motivos[motivo] = motivos.get(motivo, 0) + 1

    def _vincular_pagamento(self, arquivo, analise):
        if analise['categoria'] not in {'pagamento_colaborador', 'reembolso'} or analise['motivos']:
            return
        identificador = analise['identificador'] or f'arquivo:{arquivo.sha256}'
        pagamento = PagamentoColaborador.objects.filter(
            identificador_transacao=identificador
        ).first()
        if pagamento:
            self.contadores['pagamentos_existentes'] += 1
        else:
            data_pagamento = analise['data_pagamento']
            competencia = (
                data_pagamento.replace(day=1)
                if analise['subcategoria'] in {
                    'salario', 'salario_beneficios', 'prestacao_servico',
                    'freelancer', 'distrato', 'auxilio_telefonia', 'adiantamento',
                }
                else data_pagamento
            )
            competencia_fim = (
                competencia.replace(day=monthrange(competencia.year, competencia.month)[1])
                if competencia.day == 1 and analise['subcategoria'] in {
                    'salario', 'salario_beneficios', 'prestacao_servico',
                    'freelancer', 'distrato', 'auxilio_telefonia', 'adiantamento',
                }
                else competencia + (
                    timedelta(days=6)
                    if analise['subcategoria'] in {'vale_transporte', 'ajuda_custo'}
                    else timedelta(0)
                )
            )
            pagamento = PagamentoColaborador(
                colaborador=analise['colaborador'],
                tipo=analise['subcategoria'],
                competencia=competencia,
                competencia_fim=competencia_fim,
                valor=analise['valor'],
                data_vencimento=data_pagamento,
                status='pago',
                data_pagamento=data_pagamento,
                recorrente=analise['subcategoria'] in {'vale_transporte', 'ajuda_custo'},
                observacao=f'Importado do arquivo {arquivo.nome_original}',
                identificador_transacao=identificador,
                criado_por=self.usuario,
            )
            pagamento.full_clean()
            pagamento.save()
            self.contadores['pagamentos_criados'] += 1
        arquivo.content_type = ContentType.objects.get_for_model(pagamento)
        arquivo.object_id = pagamento.pk
        arquivo.status = 'vinculado'
        arquivo.save(update_fields=['content_type', 'object_id', 'status', 'atualizado_em'])

    def _vincular_documento_trabalhista(self, arquivo, analise):
        if (
            analise['categoria'] != 'documento_trabalhista'
            or analise['subcategoria'] != 'rescisao'
            or not analise['colaborador']
        ):
            return
        arquivo.content_type = ContentType.objects.get_for_model(Colaborador)
        arquivo.object_id = analise['colaborador'].pk
        arquivo.status = 'vinculado'
        arquivo.save(update_fields=['content_type', 'object_id', 'status', 'atualizado_em'])
