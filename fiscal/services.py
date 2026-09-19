import calendar
import hashlib
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from admissional.models import Colaborador, PagamentoColaborador
from core.models import ArquivoImportado

from .models import BeneficioFiscal, FolhaFiscal, ItemFolhaFiscal, ParcelaBeneficioFiscal


NS = {
    'm': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
REL_ID = f'{{{NS["r"]}}}id'
MONEY = Decimal('0.01')
FORMULA_ERRORS = {'#REF!', '#DIV/0!', '#VALUE!', '#NAME?', '#N/A', '#NUM!', '#NULL!'}


def normalizar_texto(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return re.sub(r'\s+', ' ', value).strip().upper()


def normalizar_documento(value):
    return re.sub(r'\D', '', str(value or ''))


def decimal_value(value):
    if value is None or value == '' or str(value).upper() in FORMULA_ERRORS:
        return None
    text = str(value).strip()
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return Decimal(text).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def excel_date(value):
    if value in (None, '') or str(value).upper() in FORMULA_ERRORS:
        return None
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    text = str(value).strip()
    try:
        serial = float(text)
    except ValueError:
        for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
    if serial <= 0:
        return None
    try:
        return date(1899, 12, 30) + timedelta(days=int(serial))
    except (OverflowError, ValueError):
        return None


class XlsxReader:
    """Leitor XLSX mínimo, sem macros nem fórmulas executadas."""

    def __init__(self, content):
        self.content = content
        try:
            self.archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValidationError('O arquivo enviado não é uma planilha XLSX válida.') from exc
        self._validate_members()
        self.shared_strings = self._read_shared_strings()
        self.fill_colors, self.style_fills = self._read_styles()
        self.sheets = self._read_sheet_paths()

    def _validate_members(self):
        names = self.archive.namelist()
        if '[Content_Types].xml' not in names or 'xl/workbook.xml' not in names:
            raise ValidationError('Estrutura interna da planilha XLSX inválida.')
        total = sum(item.file_size for item in self.archive.infolist())
        if total > 100 * 1024 * 1024:
            raise ValidationError('A planilha descompactada excede o limite de 100 MB.')

    def _read_shared_strings(self):
        if 'xl/sharedStrings.xml' not in self.archive.namelist():
            return []
        root = ET.fromstring(self.archive.read('xl/sharedStrings.xml'))
        return [
            ''.join(node.text or '' for node in item.findall('.//m:t', NS))
            for item in root.findall('m:si', NS)
        ]

    def _read_styles(self):
        if 'xl/styles.xml' not in self.archive.namelist():
            return [], []
        root = ET.fromstring(self.archive.read('xl/styles.xml'))
        colors = []
        fills_node = root.find('m:fills', NS)
        for fill in list(fills_node or []):
            pattern = fill.find('m:patternFill', NS)
            color = pattern.find('m:fgColor', NS) if pattern is not None else None
            colors.append((color.attrib.get('rgb', '').upper() if color is not None else ''))
        style_fills = []
        cell_xfs = root.find('m:cellXfs', NS)
        for style in list(cell_xfs or []):
            style_fills.append(int(style.attrib.get('fillId', 0)))
        return colors, style_fills

    def _read_sheet_paths(self):
        workbook = ET.fromstring(self.archive.read('xl/workbook.xml'))
        rels = ET.fromstring(self.archive.read('xl/_rels/workbook.xml.rels'))
        relationships = {item.attrib['Id']: item.attrib['Target'] for item in rels}
        result = {}
        for sheet in workbook.findall('m:sheets/m:sheet', NS):
            target = relationships[sheet.attrib[REL_ID]].lstrip('/')
            path = target if target.startswith('xl/') else str(PurePosixPath('xl') / target)
            result[sheet.attrib['name']] = path
        return result

    def _cell_value(self, cell):
        cell_type = cell.attrib.get('t')
        if cell_type == 'inlineStr':
            return ''.join(node.text or '' for node in cell.findall('.//m:t', NS))
        node = cell.find('m:v', NS)
        if node is None:
            return ''
        if cell_type == 's':
            try:
                return self.shared_strings[int(node.text)]
            except (ValueError, IndexError):
                return ''
        return node.text or ''

    @staticmethod
    def _column_index(reference):
        letters = re.match(r'[A-Z]+', reference).group(0)
        result = 0
        for char in letters:
            result = result * 26 + ord(char) - 64
        return result

    def rows(self, sheet_name):
        path = self.sheets[sheet_name]
        root = ET.fromstring(self.archive.read(path))
        rows = []
        for row in root.findall('.//m:sheetData/m:row', NS):
            values = {}
            for cell in row.findall('m:c', NS):
                style_id = int(cell.attrib.get('s', 0))
                fill_id = self.style_fills[style_id] if style_id < len(self.style_fills) else 0
                fill_color = self.fill_colors[fill_id] if fill_id < len(self.fill_colors) else ''
                values[self._column_index(cell.attrib['r'])] = {
                    'value': self._cell_value(cell),
                    'fill': fill_color,
                }
            rows.append((int(row.attrib['r']), values))
        return rows


SALARY_SHEETS = {
    'CLT': 'clt',
    'PJ': 'pj',
    'FREELANCE FIXO': 'freelancer',
    'SUPERVISOR': 'supervisor',
    'ADM': 'administrativo',
    'RESCISAO': 'rescisao',
}


def _header_map(rows):
    for row_number, cells in rows[:12]:
        headers = {
            normalizar_texto(cell['value']): column
            for column, cell in cells.items()
            if cell['value'] not in (None, '')
        }
        if 'COLABORADOR' in headers or 'NOME' in headers:
            return row_number, headers
    return None, {}


def _value(cells, headers, *names):
    for name in names:
        column = headers.get(normalizar_texto(name))
        if column:
            return cells.get(column, {}).get('value', '')
    return ''


def _name_cell(cells, headers):
    column = headers.get('COLABORADOR') or headers.get('NOME')
    return cells.get(column, {}) if column else {}


def _valid_name(value):
    value = normalizar_texto(value)
    return bool(value) and not value.startswith(('TOTAL', 'LEGENDA'))


def _source_status(name_cell, payment_date=None):
    color = name_cell.get('fill', '').replace('#', '').upper()
    if color.endswith('00B050') or payment_date:
        return 'pago'
    return 'pendente'


def _collaborator_index():
    by_document = {}
    by_name = {}
    for collaborator in Colaborador.objects.all().only('pk', 'nome', 'cpf', 'tipo_contrato'):
        document = normalizar_documento(collaborator.cpf)
        if document:
            by_document.setdefault(document, []).append(collaborator)
        by_name.setdefault(normalizar_texto(collaborator.nome), []).append(collaborator)
    return by_document, by_name


def _match_collaborator(document, name, by_document, by_name):
    matches = by_document.get(normalizar_documento(document), []) if document else []
    method = 'documento'
    if not matches:
        matches = by_name.get(normalizar_texto(name), [])
        method = 'nome'
    if len(matches) == 1:
        return matches[0], []
    if len(matches) > 1:
        return None, [f'Cadastro ambíguo: mais de um colaborador encontrado por {method}.']
    return None, ['Colaborador não encontrado no cadastro admissional.']


def _date_with_issue(raw, label, issues):
    parsed = excel_date(raw)
    if raw not in (None, '') and not parsed:
        issues.append(f'{label} inválida: {raw}.')
    return parsed


def _formula_issues(cells, headers):
    issues = []
    for header, column in headers.items():
        raw = str(cells.get(column, {}).get('value', '')).upper()
        if raw in FORMULA_ERRORS:
            issues.append(f'Fórmula inválida em {header}: {raw}.')
    return issues


@transaction.atomic
def importar_folha_xlsx(*, content, filename, competencia, usuario=None):
    if len(content) > 10 * 1024 * 1024:
        raise ValidationError('A planilha excede o limite de 10 MB.')
    reader = XlsxReader(content)
    digest = hashlib.sha256(content).hexdigest()
    existing = FolhaFiscal.objects.filter(hash_origem=digest).first()
    if existing:
        return existing, False

    versions = FolhaFiscal.objects.filter(competencia=competencia).values_list('versao', flat=True)
    version = max(versions, default=0) + 1
    archive = ArquivoImportado.objects.filter(sha256=digest).first()
    if not archive:
        archive = ArquivoImportado(
            categoria='planilha',
            subcategoria='folha_fiscal',
            nome_original=filename[:255],
            sha256=digest,
            tamanho=len(content),
            mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            status='arquivado',
            metadados={'competencia': competencia.isoformat(), 'tipo': 'folha_fiscal'},
            importado_por=usuario,
        )
        archive.arquivo.save(filename, ContentFile(content), save=False)
        archive.full_clean()
        archive.save()
    folha = FolhaFiscal.objects.create(
        competencia=competencia.replace(day=1),
        titulo=f'Folha Fiscal {competencia:%m/%Y}',
        versao=version,
        arquivo_origem=archive,
        hash_origem=digest,
        importado_por=usuario,
    )
    if not archive.content_type_id and not archive.object_id:
        archive.content_object = folha
        archive.status = 'vinculado'
        archive.save(update_fields=['content_type', 'object_id', 'status', 'atualizado_em'])

    by_document, by_name = _collaborator_index()
    total_issues = 0
    found_salary_sheet = False

    for original_name in reader.sheets:
        normalized_sheet = normalizar_texto(original_name)
        regime = SALARY_SHEETS.get(normalized_sheet)
        if not regime:
            continue
        found_salary_sheet = True
        rows = reader.rows(original_name)
        header_row, headers = _header_map(rows)
        if not header_row:
            folha.observacoes_importacao += f'Aba {original_name}: cabeçalho não encontrado.\n'
            total_issues += 1
            continue
        for row_number, cells in rows:
            if row_number <= header_row:
                continue
            name_cell = _name_cell(cells, headers)
            name = str(name_cell.get('value', '')).strip()
            if not _valid_name(name):
                continue
            document = _value(cells, headers, 'CPF', 'CNPJ')
            collaborator, issues = _match_collaborator(document, name, by_document, by_name)
            issues.extend(_formula_issues(cells, headers))
            start_raw = _value(cells, headers, 'ADMISSÃO', 'DATA INICIO', 'INICIO DE PRESTAÇÃO DE SERVIÇO')
            end_raw = _value(cells, headers, 'TERMINO DA PRESTAÇÃO')
            payment_raw = _value(cells, headers, 'DATA PAGAMENTO')
            start = _date_with_issue(start_raw, 'Data inicial', issues)
            end = _date_with_issue(end_raw, 'Data final', issues)
            payment_date = _date_with_issue(payment_raw, 'Data de pagamento', issues)
            planned = decimal_value(_value(cells, headers, 'SALARIO PLANEJADO', 'A RECEBER PLANEJADO'))
            execute = decimal_value(_value(cells, headers, 'SALARIO A EXECUTAR', 'A RECEBER', 'TOTAL SALARIO'))
            salary = decimal_value(_value(cells, headers, 'SALARIO', 'DIARIA/SALARIO'))
            effective_regime = 'freelancer' if salary and 0 < salary < 150 else regime
            if effective_regime == 'freelancer' and collaborator and collaborator.categoria_trabalho != 'freelancer':
                collaborator.categoria_trabalho = 'freelancer'
                collaborator.save(update_fields=['categoria_trabalho', 'atualizado_em'])
            if execute is None and regime in {'supervisor', 'administrativo'}:
                execute = salary
            if not execute and not planned:
                issues.append('Valor líquido a executar/planejado não informado.')
            item = ItemFolhaFiscal.objects.create(
                folha=folha,
                colaborador=collaborator,
                aba_origem=original_name.strip(),
                linha_origem=row_number,
                regime=effective_regime,
                nome_fonte=name[:200],
                cpf_cnpj_fonte=str(document or '')[:30],
                pix=str(_value(cells, headers, 'PIX'))[:180],
                banco=str(_value(cells, headers, 'BANCO', 'BANCO PIX', 'BANCO ITAU'))[:180],
                cargo=str(_value(cells, headers, 'CARGO'))[:180],
                contrato=str(_value(cells, headers, 'CONTRATO'))[:180],
                unidade=str(_value(cells, headers, 'UNIDADE'))[:180],
                data_inicio=start,
                data_termino=end,
                salario_base=salary,
                valor_dia=decimal_value(_value(cells, headers, 'VALOR DO DIA (R$)', 'VALOR DIA', 'DIARIA')),
                dias_trabalhados=decimal_value(_value(cells, headers, 'DIAS TRABALHADOS', 'QTD SEMANA')),
                bonificacao=decimal_value(_value(cells, headers, 'BONIFICAÇÃO')) or 0,
                faltas=decimal_value(_value(cells, headers, 'FALTAS', 'FALTA')) or 0,
                descontos=decimal_value(_value(cells, headers, 'DESCONTOS', 'DESCONTAR')) or 0,
                valor_executar=execute,
                valor_planejado=planned,
                data_pagamento_fonte=payment_date,
                status_fonte=_source_status(name_cell, payment_date),
                status_conciliacao='conciliado' if collaborator and not issues else 'revisar',
                problemas=issues,
                observacoes=str(_value(cells, headers, 'OBSERVAÇÕES')),
            )
            total_issues += len(item.problemas)

    benefit_sheet = next(
        (name for name in reader.sheets if normalizar_texto(name) == 'AJUDA DE CUSTO GERAL'),
        None,
    )
    if benefit_sheet:
        rows = reader.rows(benefit_sheet)
        header_row, headers = _header_map(rows)
        if header_row:
            for row_number, cells in rows:
                if row_number <= header_row:
                    continue
                name_cell = _name_cell(cells, headers)
                name = str(name_cell.get('value', '')).strip()
                if not _valid_name(name):
                    continue
                collaborator, issues = _match_collaborator('', name, by_document, by_name)
                issues.extend(_formula_issues(cells, headers))
                weeks = [
                    decimal_value(_value(cells, headers, f'{week}º SEMANA')) or Decimal('0')
                    for week in range(1, 5)
                ]
                if not any(value > 0 for value in weeks):
                    issues.append('Nenhum valor semanal informado.')
                benefit_type = (
                    'ajuda_custo'
                    if collaborator and collaborator.tipo_contrato == 'pj'
                    else 'vale_transporte'
                )
                benefit = BeneficioFiscal.objects.create(
                    folha=folha,
                    colaborador=collaborator,
                    aba_origem=benefit_sheet.strip(),
                    linha_origem=row_number,
                    nome_fonte=name[:200],
                    pix=str(_value(cells, headers, 'PIX'))[:180],
                    base=str(_value(cells, headers, 'BASE'))[:180],
                    contrato=str(_value(cells, headers, 'CONTRATO'))[:180],
                    tipo=benefit_type,
                    valor_passagem_diaria=decimal_value(_value(cells, headers, 'VALOR PASSAGEM DIARIA')),
                    status_fonte=_source_status(name_cell),
                    status_conciliacao='conciliado' if collaborator and not issues else 'revisar',
                    problemas=issues,
                )
                ParcelaBeneficioFiscal.objects.bulk_create([
                    ParcelaBeneficioFiscal(
                        beneficio=benefit,
                        folha=folha,
                        semana=week,
                        valor=value,
                    )
                    for week, value in enumerate(weeks, start=1)
                ])
                total_issues += len(issues)
        else:
            folha.observacoes_importacao += f'Aba {benefit_sheet}: cabeçalho não encontrado.\n'
            total_issues += 1

    if not found_salary_sheet:
        raise ValidationError('Nenhuma aba de folha reconhecida foi encontrada.')
    folha.status = 'revisao' if total_issues else 'pronta'
    folha.observacoes_importacao += f'{total_issues} ocorrência(s) encaminhada(s) para revisão.'
    folha.save(update_fields=['status', 'observacoes_importacao', 'atualizado_em'])
    return folha, True


def _month_end(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


@transaction.atomic
def gerar_pagamentos_fiscais(folha, usuario=None):
    created = 0
    skipped = 0
    type_by_regime = {
        'clt': 'salario',
        'pj': 'prestacao_servico',
        'freelancer': 'freelancer',
        'supervisor': 'prestacao_servico',
        'administrativo': 'salario',
        'rescisao': 'distrato',
    }
    for item in folha.itens.select_related('colaborador', 'pagamento'):
        value = item.valor_para_pagamento
        if item.pagamento_id or not item.colaborador_id or item.problemas or not value or value <= 0:
            skipped += 1
            continue
        transaction_id = f'fiscal:{folha.pk}:item:{item.pk}'
        payment = PagamentoColaborador.objects.filter(
            identificador_transacao=transaction_id
        ).first()
        if not payment:
            payment = PagamentoColaborador(
                identificador_transacao=transaction_id,
                colaborador=item.colaborador,
                tipo=type_by_regime[item.regime],
                competencia=folha.competencia,
                competencia_fim=_month_end(folha.competencia),
                valor=value,
                data_vencimento=item.data_pagamento_fonte or _month_end(folha.competencia),
                status='pago' if item.status_fonte == 'pago' else 'pendente',
                data_pagamento=item.data_pagamento_fonte,
                observacao=f'Importado da folha Fiscal {folha.competencia:%m/%Y}, aba {item.aba_origem}, linha {item.linha_origem}.',
                criado_por=usuario,
            )
            payment.full_clean()
            payment.save()
            created += 1
        item.pagamento = payment
        item.save(update_fields=['pagamento'])

    for installment in folha.parcelas_beneficio.select_related('beneficio__colaborador', 'pagamento'):
        benefit = installment.beneficio
        if installment.pagamento_id or not benefit.colaborador_id or benefit.problemas or installment.valor <= 0:
            skipped += 1
            continue
        start = folha.competencia + timedelta(days=(installment.semana - 1) * 7)
        transaction_id = f'fiscal:{folha.pk}:beneficio:{installment.pk}'
        payment = PagamentoColaborador.objects.filter(
            identificador_transacao=transaction_id
        ).first()
        if not payment:
            payment = PagamentoColaborador(
                identificador_transacao=transaction_id,
                colaborador=benefit.colaborador,
                tipo=benefit.tipo,
                competencia=start,
                competencia_fim=start + timedelta(days=6),
                valor=installment.valor,
                data_vencimento=start,
                status='pago' if benefit.status_fonte == 'pago' else 'pendente',
                observacao=f'Importado da folha Fiscal {folha.competencia:%m/%Y}, semana {installment.semana}.',
                criado_por=usuario,
            )
            payment.full_clean()
            payment.save()
            created += 1
        installment.pagamento = payment
        installment.save(update_fields=['pagamento'])

    has_review = (
        folha.itens.filter(status_conciliacao='revisar').exists()
        or folha.beneficios.filter(status_conciliacao='revisar').exists()
    )
    folha.status = 'revisao' if has_review else 'processada'
    folha.save(update_fields=['status', 'atualizado_em'])
    return created, skipped
