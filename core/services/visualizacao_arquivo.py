from pathlib import Path
import io
import re
import zipfile
from xml.etree import ElementTree


LIMITE_PREVIEW_OFFICE = 15 * 1024 * 1024
LIMITE_PREVIEW_TEXTO = 512 * 1024


def _ler_bytes(arquivo, limite):
    if arquivo.tamanho and arquivo.tamanho > limite:
        raise ValueError('Arquivo grande demais para a pré-visualização interna.')
    with arquivo.arquivo.open('rb') as stream:
        dados = stream.read(limite + 1)
    if len(dados) > limite:
        raise ValueError('Arquivo grande demais para a pré-visualização interna.')
    return dados


def _preview_docx(arquivo):
    dados = _ler_bytes(arquivo, LIMITE_PREVIEW_OFFICE)
    with zipfile.ZipFile(io.BytesIO(dados)) as pacote:
        raiz = ElementTree.fromstring(pacote.read('word/document.xml'))
    paragrafos = []
    for elemento in raiz.iter():
        if elemento.tag.rsplit('}', 1)[-1] != 'p':
            continue
        texto = ''.join(
            item.text or '' for item in elemento.iter()
            if item.tag.rsplit('}', 1)[-1] == 't'
        ).strip()
        if texto:
            paragrafos.append(texto)
        if len(paragrafos) >= 300:
            break
    return {'kind': 'docx', 'paragraphs': paragrafos}


def _indice_coluna(referencia):
    letras = re.match(r'[A-Z]+', referencia or '')
    if not letras:
        return 0
    indice = 0
    for letra in letras.group(0):
        indice = indice * 26 + ord(letra) - 64
    return indice - 1


def _preview_xlsx(arquivo):
    dados = _ler_bytes(arquivo, LIMITE_PREVIEW_OFFICE)
    with zipfile.ZipFile(io.BytesIO(dados)) as pacote:
        nomes = set(pacote.namelist())
        compartilhados = []
        if 'xl/sharedStrings.xml' in nomes:
            raiz_strings = ElementTree.fromstring(pacote.read('xl/sharedStrings.xml'))
            compartilhados = [
                ''.join(
                    item.text or '' for item in si.iter()
                    if item.tag.rsplit('}', 1)[-1] == 't'
                )
                for si in raiz_strings
            ]

        workbook = ElementTree.fromstring(pacote.read('xl/workbook.xml'))
        rels = ElementTree.fromstring(pacote.read('xl/_rels/workbook.xml.rels'))
        destinos = {
            rel.attrib.get('Id'): rel.attrib.get('Target', '')
            for rel in rels
        }
        planilhas = []
        for sheet in workbook.iter():
            if sheet.tag.rsplit('}', 1)[-1] != 'sheet':
                continue
            rel_id = next(
                (valor for chave, valor in sheet.attrib.items() if chave.endswith('}id')),
                '',
            )
            destino = destinos.get(rel_id, '')
            caminho = destino.lstrip('/')
            if not caminho.startswith('xl/'):
                caminho = f'xl/{caminho}'
            if caminho not in nomes:
                continue
            raiz_aba = ElementTree.fromstring(pacote.read(caminho))
            linhas = []
            for row in raiz_aba.iter():
                if row.tag.rsplit('}', 1)[-1] != 'row':
                    continue
                valores = []
                for cell in row:
                    if cell.tag.rsplit('}', 1)[-1] != 'c':
                        continue
                    coluna = _indice_coluna(cell.attrib.get('r', ''))
                    if coluna >= 20:
                        continue
                    while len(valores) <= coluna:
                        valores.append('')
                    tipo = cell.attrib.get('t', '')
                    valor = ''
                    if tipo == 'inlineStr':
                        valor = ''.join(
                            item.text or '' for item in cell.iter()
                            if item.tag.rsplit('}', 1)[-1] == 't'
                        )
                    else:
                        no_valor = next(
                            (item for item in cell if item.tag.rsplit('}', 1)[-1] == 'v'),
                            None,
                        )
                        valor = no_valor.text if no_valor is not None and no_valor.text else ''
                        if tipo == 's' and valor.isdigit():
                            indice = int(valor)
                            if indice < len(compartilhados):
                                valor = compartilhados[indice]
                        elif tipo == 'b':
                            valor = 'Sim' if valor == '1' else 'Não'
                    valores[coluna] = valor
                if any(str(valor).strip() for valor in valores):
                    linhas.append(valores)
                if len(linhas) >= 100:
                    break
            planilhas.append({'name': sheet.attrib.get('name', 'Planilha'), 'rows': linhas})
            if len(planilhas) >= 3:
                break
    return {'kind': 'xlsx', 'sheets': planilhas}


def preparar_preview(arquivo):
    extensao = Path(arquivo.nome_original or arquivo.arquivo.name).suffix.lower()
    if extensao == '.pdf' or arquivo.mime_type == 'application/pdf':
        return {'kind': 'pdf'}
    if extensao in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}:
        return {'kind': 'image'}
    try:
        if extensao == '.docx':
            return _preview_docx(arquivo)
        if extensao == '.xlsx':
            return _preview_xlsx(arquivo)
        if extensao in {'.xml', '.txt', '.csv', '.json', '.log'}:
            dados = _ler_bytes(arquivo, LIMITE_PREVIEW_TEXTO)
            return {'kind': 'text', 'text': dados.decode('utf-8', errors='replace')}
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        return {'kind': 'unavailable', 'error': str(exc)}
    return {'kind': 'download'}
