"""Indexacao e extracao local dos documentos persistidos no Storage.

O processamento e idempotente: o SHA-256 identifica o arquivo, a origem no
Storage e registrada uma unica vez e os objetos de negocio usam chaves
naturais antes de qualquer criacao.
"""
from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from admissional.models import Colaborador, PagamentoColaborador
from core.models import ArquivoImportado, OrigemArquivoImportado
from core.services.importacao_arquivo_central import (
    area_responsavel, classificar, classificar_pagamento_regra,
    extrair_beneficiario, extrair_data, extrair_identificador, extrair_valor,
    localizar_colaborador, nome_indicado,
)
from core.storage_organization import FILE_FIELDS, iter_storage_files
from financeiro.models import AuditoriaItem, DocumentoFinanceiro, ItemDocumentoFinanceiro


MAX_TEXTO_BANCO = 120_000
MAX_ARQUIVO_LEITURA = 50 * 1024 * 1024
ORIGEM_STORAGE = 'storage://'
_OCR_ENGINE = None


def _sha256(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _nome_local(tag):
    return str(tag).rsplit('}', 1)[-1]


def _texto_docx(conteudo):
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        raiz = ElementTree.fromstring(pacote.read('word/document.xml'))
    return '\n'.join(
        elemento.text or '' for elemento in raiz.iter()
        if _nome_local(elemento.tag) == 't'
    )


def _texto_xlsx(conteudo):
    """Extrai valores visiveis sem carregar formulas ou macros."""
    linhas = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        compartilhados = []
        if 'xl/sharedStrings.xml' in pacote.namelist():
            raiz = ElementTree.fromstring(pacote.read('xl/sharedStrings.xml'))
            for item in raiz:
                compartilhados.append(''.join(
                    no.text or '' for no in item.iter() if _nome_local(no.tag) == 't'
                ))
        planilhas = sorted(
            nome for nome in pacote.namelist()
            if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', nome)
        )
        for indice, nome in enumerate(planilhas, 1):
            linhas.append(f'[Planilha {indice}]')
            raiz = ElementTree.fromstring(pacote.read(nome))
            for linha in (no for no in raiz.iter() if _nome_local(no.tag) == 'row'):
                valores = []
                for celula in (no for no in linha if _nome_local(no.tag) == 'c'):
                    tipo = celula.attrib.get('t', '')
                    valor = ''
                    for no in celula.iter():
                        if _nome_local(no.tag) in {'v', 't'} and no.text is not None:
                            valor = no.text
                            break
                    if tipo == 's' and valor.isdigit():
                        posicao = int(valor)
                        valor = compartilhados[posicao] if posicao < len(compartilhados) else valor
                    valores.append(valor)
                if any(valor.strip() for valor in valores):
                    linhas.append(' | '.join(valores))
                if sum(len(item) for item in linhas) >= MAX_TEXTO_BANCO:
                    return '\n'.join(linhas)[:MAX_TEXTO_BANCO]
    return '\n'.join(linhas)


def _ocr_imagem(conteudo):
    global _OCR_ENGINE
    try:
        import cv2
        import numpy
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return ''
    imagem = cv2.imdecode(numpy.frombuffer(conteudo, dtype=numpy.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        return ''
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    resultado, _ = _OCR_ENGINE(imagem)
    if not resultado:
        return ''
    return '\n'.join(str(item[1]) for item in resultado if len(item) > 1)


def _texto_pdf(conteudo, usar_ocr=True):
    import pymupdf

    textos = []
    with pymupdf.open(stream=conteudo, filetype='pdf') as documento:
        for pagina in documento:
            texto = pagina.get_text().strip()
            if usar_ocr and len(texto) < 40:
                imagem = pagina.get_pixmap(matrix=pymupdf.Matrix(1.7, 1.7), alpha=False)
                texto_ocr = _ocr_imagem(imagem.tobytes('png'))
                if texto_ocr:
                    texto = texto_ocr
            textos.append(texto)
            if sum(len(item) for item in textos) >= MAX_TEXTO_BANCO:
                break
    return '\n'.join(textos)[:MAX_TEXTO_BANCO]


def _elementos_xml(conteudo):
    raiz = ElementTree.fromstring(conteudo)
    elementos = {}
    for elemento in raiz.iter():
        chave = _nome_local(elemento.tag)
        if elemento.text and elemento.text.strip():
            elementos.setdefault(chave, elemento.text.strip())
    return raiz, elementos


def _decimal(valor):
    if valor in (None, ''):
        return None
    texto = re.sub(r'[^\d,.-]', '', str(valor)).strip()
    if not texto:
        return None
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _data(valor):
    if not valor:
        return None
    texto = str(valor).strip()
    data_iso = parse_date(texto[:10])
    if data_iso:
        return data_iso
    momento = parse_datetime(texto)
    if momento:
        return momento.date()
    for formato in ('%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%y', '%d-%m-%y', '%d.%m.%y'):
        try:
            resultado = datetime.strptime(texto, formato).date()
            return resultado.replace(year=resultado.year + 2000) if resultado.year < 2000 else resultado
        except ValueError:
            continue
    return None


def _primeiro(padroes, texto):
    for padrao in padroes:
        encontrado = re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)
        if encontrado:
            return encontrado.group(1).strip()
    return ''


def _metadados_genericos(texto, nome):
    valor = extrair_valor(texto)
    data_documento = extrair_data(texto, nome)
    return {
        'beneficiario': extrair_beneficiario(texto),
        'valor': f'{valor:.2f}'.replace('.', ',') if valor is not None else '',
        'data_pagamento': data_documento.isoformat() if data_documento else '',
        'identificador_transacao': extrair_identificador(texto),
        'cnpj': _primeiro([r'\bCNPJ(?:/CPF)?\s*[:\-]?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})'], texto),
        'cpf': _primeiro([r'\bCPF\s*[:\-]?\s*(\d{3}\.?\d{3}\.?\d{3}-?\d{2})'], texto),
        'numero_documento': _primeiro([
            r'(?:N[ÚU]MERO|N[º°O])\s*(?:DA\s+NF(?:-E|SE)?)?\s*[:#\-]?\s*(\d{1,30})',
            r'NF(?:-E|SE)?\s*[:#\-]?\s*(\d{1,30})',
        ], texto),
    }


def _metadados_xml(conteudo):
    raiz, elementos = _elementos_xml(conteudo)
    numero = next((elementos.get(chave) for chave in ('nNF', 'nNFSe', 'Numero') if elementos.get(chave)), '')
    valor = next((elementos.get(chave) for chave in ('vNF', 'vLiq', 'vServ', 'ValorServicos') if elementos.get(chave)), '')
    emissao = next((elementos.get(chave) for chave in ('dhEmi', 'dEmi', 'DataEmissao') if elementos.get(chave)), '')
    vencimento = next((elementos.get(chave) for chave in ('dVenc', 'DataVencimento') if elementos.get(chave)), '')
    descricao = next((elementos.get(chave) for chave in ('xDescServ', 'Discriminacao', 'xProd', 'xTribNac') if elementos.get(chave)), '')
    itens = []
    for detalhe in (no for no in raiz.iter() if _nome_local(no.tag) == 'det'):
        dados = {}
        for no in detalhe.iter():
            chave = _nome_local(no.tag)
            if no.text and no.text.strip() and chave not in dados:
                dados[chave] = no.text.strip()
        if dados.get('xProd'):
            itens.append({
                'descricao_produto': dados.get('xProd', '')[:255],
                'ncm': dados.get('NCM', '')[:20],
                'quantidade': dados.get('qCom', '1'),
                'valor_unitario': dados.get('vUnCom', '0'),
                'valor_total': dados.get('vProd', '0'),
            })
    return {
        'numero_documento': numero,
        'valor': str(valor).replace('.', ',') if valor else '',
        'data_emissao': (_data(emissao).isoformat() if _data(emissao) else ''),
        'data_vencimento': (_data(vencimento).isoformat() if _data(vencimento) else ''),
        'cnpj_emitente': elementos.get('CNPJ', ''),
        'razao_social_emitente': elementos.get('xNome') or elementos.get('RazaoSocial', ''),
        'unidade': elementos.get('xLocPrestacao') or elementos.get('Municipio', ''),
        'descricao': descricao[:2000],
        'itens': itens,
    }


def extrair_documento(conteudo, nome, mime_type='', *, usar_ocr=True):
    extensao = Path(nome).suffix.lower()
    texto = ''
    estruturados = {}
    metodo = 'nome_arquivo'
    if extensao == '.pdf':
        texto = _texto_pdf(conteudo, usar_ocr=usar_ocr)
        metodo = 'pdf_texto_ocr_local' if usar_ocr else 'pdf_texto'
    elif extensao in {'.jpg', '.jpeg', '.png'}:
        texto = _ocr_imagem(conteudo) if usar_ocr else ''
        metodo = 'ocr_local' if texto else 'nome_arquivo'
    elif extensao == '.xml':
        _, elementos = _elementos_xml(conteudo)
        texto = '\n'.join(f'{chave}: {valor}' for chave, valor in elementos.items())
        estruturados = _metadados_xml(conteudo)
        metodo = 'xml_estruturado'
    elif extensao == '.docx':
        texto = _texto_docx(conteudo)
        metodo = 'docx_texto'
    elif extensao == '.xlsx':
        texto = _texto_xlsx(conteudo)
        metodo = 'xlsx_celulas'
    genericos = _metadados_genericos(texto, nome)
    return texto[:MAX_TEXTO_BANCO], {**genericos, **{k: v for k, v in estruturados.items() if v not in ('', None, [])}}, metodo


def _dados_origem(arquivo):
    origem = arquivo.origens.order_by('modificado_em', 'pk').first()
    caminho = Path(origem.caminho_relativo) if origem else Path(arquivo.nome_original)
    return origem, caminho


def _data_documento(metadados, origem=None):
    for chave in ('data_emissao', 'data_pagamento', 'data_vencimento'):
        encontrada = _data(metadados.get(chave))
        if encontrada:
            return encontrada, chave
    if origem and origem.modificado_em:
        return origem.modificado_em.date(), 'arquivo_modificado'
    return None, ''


def _vincular_pagamento(arquivo, usuario, metadados, caminho):
    if arquivo.categoria not in {'pagamento_colaborador', 'reembolso'}:
        return None
    beneficiario = metadados.get('beneficiario', '')
    indicado = metadados.get('nome_indicado') or nome_indicado(caminho, arquivo.subcategoria)
    colaborador, pontos, confiavel = localizar_colaborador(
        beneficiario or indicado, list(Colaborador.objects.all()), metadados.get('unidade_origem', '')
    )
    valor = _decimal(metadados.get('valor'))
    data_pagamento = _data(metadados.get('data_pagamento'))
    tipo = classificar_pagamento_regra(arquivo.subcategoria, data_pagamento, valor, colaborador)
    metadados.update({
        'nome_indicado': indicado,
        'pontuacao_colaborador': round(pontos, 3),
        'colaborador_sugerido_id': colaborador.pk if confiavel and colaborador else None,
    })
    tipos = dict(PagamentoColaborador.TIPOS)
    faltantes = []
    if not colaborador or not confiavel:
        faltantes.append('colaborador')
    if not valor or valor <= 0:
        faltantes.append('valor')
    if not data_pagamento:
        faltantes.append('data')
    if tipo not in tipos:
        faltantes.append('tipo')
    if faltantes:
        arquivo.status = 'revisar'
        arquivo.motivo_revisao = 'Dados preservados, mas sem vínculo automático: ' + ', '.join(faltantes) + '.'
        return None
    identificador = metadados.get('identificador_transacao') or f'storage:{arquivo.sha256}'
    pagamento = PagamentoColaborador.objects.filter(identificador_transacao=identificador).first()
    if not pagamento:
        mensal = tipo in {'salario', 'salario_beneficios', 'prestacao_servico', 'freelancer', 'distrato', 'auxilio_telefonia'}
        competencia = data_pagamento.replace(day=1) if mensal else data_pagamento
        competencia_fim = (
            competencia.replace(day=monthrange(competencia.year, competencia.month)[1])
            if mensal else data_pagamento + (timedelta(days=6) if tipo in {'vale_transporte', 'ajuda_custo'} else timedelta())
        )
        pagamento = PagamentoColaborador(
            colaborador=colaborador, tipo=tipo, competencia=competencia,
            competencia_fim=competencia_fim, valor=valor,
            data_vencimento=data_pagamento, status='pago',
            data_pagamento=data_pagamento,
            recorrente=tipo in {'vale_transporte', 'ajuda_custo'},
            observacao=f'Importado automaticamente do Storage: {arquivo.nome_original}',
            identificador_transacao=identificador, criado_por=usuario,
        )
        pagamento.full_clean()
        pagamento.save()
    arquivo.content_type = ContentType.objects.get_for_model(pagamento)
    arquivo.object_id = pagamento.pk
    arquivo.status = 'vinculado'
    arquivo.motivo_revisao = ''
    arquivo.subcategoria = tipo
    return pagamento


def _tipo_financeiro(arquivo):
    if arquivo.categoria == 'nota_fiscal':
        return 'nota_fiscal'
    if arquivo.subcategoria == 'boleto':
        return 'boleto'
    if arquivo.subcategoria == 'recibo':
        return 'recibo'
    return 'pagamento'


def _vincular_financeiro(arquivo, usuario, metadados):
    if arquivo.categoria not in {'nota_fiscal', 'documento_financeiro'}:
        return None
    numero = str(metadados.get('numero_documento') or '').strip()[:50]
    valor = _decimal(metadados.get('valor'))
    emissao = _data(metadados.get('data_emissao') or metadados.get('data_pagamento'))
    cnpj = re.sub(r'\D', '', str(metadados.get('cnpj_emitente') or metadados.get('cnpj') or ''))[:18]
    if not numero or not valor or valor <= 0 or not emissao:
        if arquivo.status != 'vinculado':
            arquivo.status = 'revisar'
            arquivo.motivo_revisao = 'Dados preservados; número, valor ou data insuficientes para criar o documento financeiro.'
        return None
    consulta = DocumentoFinanceiro.objects.filter(
        numero_documento=numero, valor=valor, data_emissao=emissao,
    )
    if cnpj:
        consulta = consulta.filter(cnpj_emitente=cnpj)
    documento = consulta.order_by('pk').first()
    if not documento:
        descricao = str(metadados.get('descricao') or arquivo.nome_original)[:300]
        documento = DocumentoFinanceiro.objects.create(
            tipo=_tipo_financeiro(arquivo), numero_documento=numero,
            descricao=descricao, valor=valor,
            unidade=str(metadados.get('unidade') or metadados.get('unidade_origem') or '')[:100],
            cnpj_emitente=cnpj,
            razao_social_emitente=str(metadados.get('razao_social_emitente') or '')[:200],
            data_emissao=emissao,
            data_vencimento=_data(metadados.get('data_vencimento')),
            status='recebido', recebido_por=usuario,
        )
        for item, _ in AuditoriaItem.ITENS_CHECKLIST:
            AuditoriaItem.objects.get_or_create(documento=documento, item=item)
    for item in metadados.get('itens') or []:
        descricao = str(item.get('descricao_produto') or '')[:255]
        quantidade = _decimal(item.get('quantidade')) or Decimal('1')
        unitario = _decimal(item.get('valor_unitario')) or Decimal('0')
        total = _decimal(item.get('valor_total')) or Decimal('0')
        if descricao:
            ItemDocumentoFinanceiro.objects.get_or_create(
                documento=documento, descricao_produto=descricao,
                ncm=str(item.get('ncm') or '')[:20], quantidade=quantidade,
                valor_unitario=unitario, valor_total=total,
            )
    if not documento.itens.exists() and metadados.get('descricao'):
        ItemDocumentoFinanceiro.objects.get_or_create(
            documento=documento,
            descricao_produto=str(metadados['descricao'])[:255],
            quantidade=Decimal('1'), valor_unitario=valor, valor_total=valor,
        )
    arquivo.content_type = ContentType.objects.get_for_model(documento)
    arquivo.object_id = documento.pk
    arquivo.status = 'vinculado'
    arquivo.motivo_revisao = ''
    return documento


def _classificacao_nativa(model_label, instance, field_name):
    if model_label.startswith('admissional.'):
        return 'documento_trabalhista', getattr(instance, 'tipo', field_name), 'rh'
    if model_label == 'financeiro.DocumentoFinanceiro':
        return ('nota_fiscal' if instance.tipo == 'nota_fiscal' else 'documento_financeiro', instance.tipo, 'financeiro')
    if model_label.startswith('compras.'):
        return 'pedido', field_name, 'compras'
    if model_label.startswith('sesmet.'):
        return 'outro', field_name, 'sesmet'
    if model_label.startswith('manutencao.'):
        return 'outro', field_name, 'manutencao'
    if model_label.startswith('recrutamento.'):
        return 'outro', field_name, 'recrutamento'
    return 'outro', field_name, 'geral'


def indexar_storage(*, usuario=None, progresso=None):
    progresso = progresso or (lambda mensagem: None)
    por_chave = {}
    for model_label, campos in FILE_FIELDS.items():
        model = apps.get_model(model_label)
        for instance in model.objects.iterator():
            for campo in campos:
                arquivo_campo = getattr(instance, campo)
                if arquivo_campo and arquivo_campo.name:
                    por_chave.setdefault(arquivo_campo.name, []).append((model_label, instance, campo))
    chaves = list(iter_storage_files(default_storage))
    contadores = {'storage': len(chaves), 'indexados': 0, 'origens': 0, 'erros': 0}
    origens_existentes = set(
        OrigemArquivoImportado.objects.filter(
            caminho_relativo__startswith=ORIGEM_STORAGE
        ).values_list('caminho_relativo', flat=True)
    )
    origens_centrais = []
    agora = timezone.now()
    for chave in chaves:
        origem_nome = f'{ORIGEM_STORAGE}{chave}'
        if origem_nome in origens_existentes:
            continue
        referencia_central = next(
            (
                instance for model_label, instance, _campo in por_chave.get(chave, [])
                if model_label == 'core.ArquivoImportado'
            ),
            None,
        )
        if referencia_central is not None:
            origens_centrais.append(OrigemArquivoImportado(
                arquivo_importado=referencia_central,
                caminho_relativo=origem_nome,
                pasta_raiz='Storage Supabase',
                modificado_em=agora,
            ))
            origens_existentes.add(origem_nome)
    if origens_centrais:
        OrigemArquivoImportado.objects.bulk_create(
            origens_centrais, batch_size=500, ignore_conflicts=True
        )
        contadores['origens'] += len(origens_centrais)
    for indice, chave in enumerate(chaves, 1):
        origem_nome = f'{ORIGEM_STORAGE}{chave}'
        if origem_nome in origens_existentes:
            continue
        try:
            referencias = por_chave.get(chave, [])
            falha_tamanho = False
            try:
                tamanho = default_storage.size(chave) or 0
            except Exception:
                tamanho = 0
                falha_tamanho = True
            if tamanho > MAX_ARQUIVO_LEITURA:
                raise ValueError('Arquivo acima de 50 MB')
            if falha_tamanho:
                conteudo = b''
            else:
                with default_storage.open(chave, 'rb') as stream:
                    conteudo = stream.read()
            digest = _sha256(conteudo)
            arquivo = ArquivoImportado.objects.filter(sha256=digest).first()
            if not arquivo:
                if referencias:
                    model_label, instance, campo = referencias[0]
                    categoria, subcategoria, area = _classificacao_nativa(model_label, instance, campo)
                else:
                    categoria, subcategoria = classificar(Path(chave))
                    area = area_responsavel(categoria, subcategoria)
                arquivo = ArquivoImportado(
                    categoria=categoria, subcategoria=subcategoria, area=area,
                    nome_original=PurePosixPath(chave).name[:255],
                    sha256=digest, tamanho=tamanho,
                    mime_type=mimetypes.guess_type(chave)[0] or 'application/octet-stream',
                    status='revisar' if chave.startswith(('_orfaos/', '_temporarios/')) else 'arquivado',
                    motivo_revisao=(
                        'Arquivo vazio recuperado do Storage.' if falha_tamanho
                        else 'Arquivo recuperado de área temporária/quarentena.'
                        if chave.startswith(('_orfaos/', '_temporarios/')) else ''
                    ),
                    importado_por=usuario,
                )
                arquivo.arquivo.name = chave
                if referencias:
                    _, instance, _ = referencias[0]
                    arquivo.content_type = ContentType.objects.get_for_model(instance)
                    arquivo.object_id = instance.pk
                    arquivo.status = 'vinculado'
                arquivo.save()
                contadores['indexados'] += 1
            _, origem_criada = OrigemArquivoImportado.objects.get_or_create(
                caminho_relativo=origem_nome,
                defaults={
                    'arquivo_importado': arquivo,
                    'pasta_raiz': 'Storage Supabase',
                    'modificado_em': timezone.now(),
                },
            )
            contadores['origens'] += int(origem_criada)
            origens_existentes.add(origem_nome)
        except Exception as exc:
            contadores['erros'] += 1
            progresso(f'Falha ao indexar {chave}: {exc}')
        if indice % 100 == 0:
            progresso(f'Indexação do Storage: {indice}/{len(chaves)}')
    return contadores


@transaction.atomic
def processar_arquivo(arquivo, *, usuario=None, usar_ocr=True, forcar=False):
    if arquivo.processado_em and not forcar:
        return {'ignorado': True}
    if not arquivo.arquivo or not default_storage.exists(arquivo.arquivo.name):
        arquivo.status = 'erro'
        arquivo.motivo_revisao = 'Arquivo não encontrado no Storage.'
        arquivo.processado_em = timezone.now()
        arquivo.save(update_fields=['status', 'motivo_revisao', 'processado_em', 'atualizado_em'])
        return {'erro': 'ausente'}
    if arquivo.tamanho > MAX_ARQUIVO_LEITURA:
        return {'erro': 'acima_limite'}
    with default_storage.open(arquivo.arquivo.name, 'rb') as stream:
        conteudo = stream.read()
    origem, caminho = _dados_origem(arquivo)
    texto, extraidos, metodo = extrair_documento(
        conteudo, arquivo.nome_original, arquivo.mime_type, usar_ocr=usar_ocr
    )
    metadados = {**(arquivo.metadados or {})}
    for chave, valor in extraidos.items():
        if valor not in ('', None, []):
            metadados[chave] = valor
    metadados['extracao'] = {
        'metodo': metodo,
        'processado_em': timezone.now().isoformat(),
        'caracteres': len(texto),
    }
    data_documento, origem_data = _data_documento(metadados, origem)
    if data_documento:
        metadados['data_documento'] = data_documento.isoformat()
        metadados['origem_data_documento'] = origem_data
    arquivo.texto_extraido = texto
    arquivo.metadados = metadados
    arquivo.data_documento = data_documento
    arquivo.processado_em = timezone.now()
    _vincular_pagamento(arquivo, usuario, metadados, caminho)
    _vincular_financeiro(arquivo, usuario, metadados)
    arquivo.metadados = metadados
    arquivo.save(update_fields=[
        'categoria', 'subcategoria', 'content_type', 'object_id', 'status',
        'motivo_revisao', 'metadados', 'data_documento', 'texto_extraido',
        'processado_em', 'atualizado_em',
    ])
    return {'ignorado': False, 'vinculado': arquivo.status == 'vinculado'}


def processar_todos(
    *, usuario=None, usar_ocr=True, forcar=False, limite=None,
    somente_sem_texto=False, workers=1, progresso=None,
):
    progresso = progresso or (lambda mensagem: None)
    queryset = ArquivoImportado.objects.prefetch_related('origens').order_by('pk')
    if somente_sem_texto:
        queryset = queryset.filter(Q(texto_extraido='') | Q(texto_extraido__isnull=True))
    elif not forcar:
        queryset = queryset.filter(processado_em__isnull=True)
    if limite:
        queryset = queryset[:limite]
    ids = list(queryset.values_list('pk', flat=True))
    contadores = {'encontrados': len(ids), 'processados': 0, 'vinculados': 0, 'ignorados': 0, 'erros': 0}

    def executar(pk):
        close_old_connections()
        try:
            arquivo = ArquivoImportado.objects.prefetch_related('origens').get(pk=pk)
            resultado = processar_arquivo(
                arquivo, usuario=usuario, usar_ocr=usar_ocr, forcar=forcar
            )
            return resultado, ''
        except Exception as exc:
            ArquivoImportado.objects.filter(pk=pk).update(
                status='erro', motivo_revisao=f'Falha no processamento local: {exc}',
                processado_em=timezone.now(),
            )
            nome = ArquivoImportado.objects.filter(pk=pk).values_list('nome_original', flat=True).first() or ''
            return {'erro': str(exc)}, f'Falha no documento #{pk} ({nome}): {exc}'
        finally:
            close_old_connections()

    def contabilizar(resultado, erro_texto, indice):
        contadores['ignorados'] += int(resultado.get('ignorado', False))
        contadores['processados'] += int(not resultado.get('ignorado', False))
        contadores['vinculados'] += int(resultado.get('vinculado', False))
        contadores['erros'] += int(bool(resultado.get('erro')))
        if erro_texto:
            progresso(erro_texto)
        if indice % 25 == 0:
            progresso(f'Processamento: {indice}/{len(ids)}')

    workers = max(1, min(int(workers or 1), 12))
    if workers == 1:
        for indice, pk in enumerate(ids, 1):
            contabilizar(*executar(pk), indice)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futuros = {executor.submit(executar, pk): pk for pk in ids}
            for indice, futuro in enumerate(as_completed(futuros), 1):
                contabilizar(*futuro.result(), indice)
    return contadores
