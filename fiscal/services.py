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
    text = str(value).strip().replace('\xa0', '').replace('R$', '').replace(' ', '')
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
    text = re.sub(r'[/.-]+', '/', str(value).strip())
    try:
        serial = float(text)
    except ValueError:
        for fmt in (
            '%d/%m/%Y', '%d/%m/%y',
            '%m/%d/%Y', '%m/%d/%y',
            '%d-%m-%Y', '%d-%m-%y',
            '%Y-%m-%d',
        ):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        partes = text.split('/')
        if len(partes) == 3 and all(parte.isdigit() for parte in partes):
            dia, mes, ano_fonte = partes
            ano_atual = date.today().year
            candidatos = []
            for ano in range(ano_atual - 8, ano_atual + 2):
                ano_texto = str(ano)
                distancia = _distancia_edicao_curta(ano_fonte, ano_texto)
                if distancia == 1:
                    try:
                        candidatos.append(
                            (abs(ano - ano_atual), datetime.strptime(
                                f'{dia}/{mes}/{ano_texto}', '%d/%m/%Y'
                            ).date())
                        )
                    except ValueError:
                        pass
            if candidatos:
                return min(candidatos, key=lambda item: item[0])[1]
        return None
    if serial <= 0:
        return None
    try:
        return date(1899, 12, 30) + timedelta(days=int(serial))
    except (OverflowError, ValueError):
        return None


def _distancia_edicao_curta(a, b):
    """Distancia Levenshtein pequena para reparar somente um digito do ano."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 1:
        return 2
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b))
    curto, longo = (a, b) if len(a) < len(b) else (b, a)
    return 1 if any(longo[:i] + longo[i + 1:] == curto for i in range(len(longo))) else 2


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
    'ATIVOS': 'pj',
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


def _match_collaborator(
    document, name, by_document, by_name, *, allow_inactive=False
):
    matches = by_document.get(normalizar_documento(document), []) if document else []
    method = 'documento'
    if not matches:
        matches = by_name.get(normalizar_texto(name), [])
        method = 'nome'
    if len(matches) == 1:
        collaborator = matches[0]
        if (
            not allow_inactive
            and collaborator.status in Colaborador.STATUS_SEM_PAGAMENTO
        ):
            return collaborator, [
                f'Colaborador {collaborator.get_status_display().lower()} no cadastro admissional.'
            ]
        return collaborator, []
    if len(matches) > 1:
        return None, [f'Cadastro ambíguo: mais de um colaborador encontrado por {method}.']
    return None, ['Colaborador não encontrado no cadastro admissional.']


def _date_with_issue(raw, label, issues):
    parsed = excel_date(raw)
    if normalizar_texto(raw) not in {'', '-', '/', 'N/A', 'NA'} and not parsed:
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
def importar_folha_xlsx(
    *, content, filename, competencia, usuario=None, include_rescisoes=False
):
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
            area='fiscal',
            nome_original=filename[:255],
            sha256=digest,
            tamanho=len(content),
            mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            status='arquivado',
            metadados={'competencia': competencia.isoformat(), 'tipo': 'folha_fiscal'},
            importado_por=usuario,
        )
        storage_name = f'folha-fiscal-{competencia:%Y-%m}-{digest[:12]}.xlsx'
        archive.arquivo.save(storage_name, ContentFile(content), save=False)
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
    archive.content_object = folha
    archive.status = 'vinculado'
    archive.save(update_fields=['content_type', 'object_id', 'status', 'atualizado_em'])

    by_document, by_name = _collaborator_index()
    total_issues = 0
    found_salary_sheet = False
    items_to_create = []
    freelancer_collaborator_ids = set()

    for original_name in reader.sheets:
        normalized_sheet = normalizar_texto(original_name)
        regime = SALARY_SHEETS.get(normalized_sheet)
        if not regime or (regime == 'rescisao' and not include_rescisoes):
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
            collaborator, issues = _match_collaborator(
                document,
                name,
                by_document,
                by_name,
                allow_inactive=regime == 'rescisao',
            )
            issues.extend(_formula_issues(cells, headers))
            start_raw = _value(
                cells,
                headers,
                'ADMISSAO',
                'DATA INICIO',
                'INICIO DE PRESTACAO DE SERVICO',
            )
            end_raw = _value(
                cells,
                headers,
                'TERMINO DA PRESTACAO',
                'DESLIGAMENTO',
            )
            payment_raw = _value(cells, headers, 'DATA PAGAMENTO')
            start = _date_with_issue(start_raw, 'Data inicial', issues)
            end = _date_with_issue(end_raw, 'Data final', issues)
            payment_date = _date_with_issue(payment_raw, 'Data de pagamento', issues)
            planned = decimal_value(_value(cells, headers, 'SALARIO PLANEJADO', 'A RECEBER PLANEJADO'))
            execute = decimal_value(_value(cells, headers, 'SALARIO A EXECUTAR', 'A RECEBER', 'TOTAL SALARIO'))
            salary = decimal_value(_value(cells, headers, 'SALARIO', 'DIARIA/SALARIO'))
            daily_rate = decimal_value(
                _value(cells, headers, 'VALOR DO DIA (R$)', 'VALOR DIA', 'DIARIA')
            )
            days_worked = decimal_value(
                _value(cells, headers, 'DIAS TRABALHADOS', 'QTD SEMANA')
            )
            effective_regime = regime
            if normalized_sheet == 'ATIVOS':
                clt_value = normalizar_texto(_value(cells, headers, 'CLT'))
                effective_regime = 'clt' if clt_value in {'SIM', 'CLT'} else 'pj'
            if effective_regime in {'clt', 'pj'} and salary and 0 < salary < 150:
                effective_regime = 'freelancer'
            if effective_regime == 'freelancer':
                if not daily_rate and salary and salary > 0:
                    daily_rate = salary
                if execute is None and planned is None and daily_rate and days_worked:
                    execute = (daily_rate * days_worked).quantize(Decimal('0.01'))
            if effective_regime == 'freelancer' and collaborator and collaborator.categoria_trabalho != 'freelancer':
                freelancer_collaborator_ids.add(collaborator.pk)
            if execute is None and regime in {'supervisor', 'administrativo'}:
                execute = salary
            if regime != 'rescisao' and not execute and not planned:
                issues.append('Valor líquido a executar/planejado não informado.')
            item = ItemFolhaFiscal(
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
                valor_dia=daily_rate,
                dias_trabalhados=days_worked,
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
            items_to_create.append(item)
            total_issues += len(item.problemas)

    if items_to_create:
        ItemFolhaFiscal.objects.bulk_create(items_to_create, batch_size=200)
    if freelancer_collaborator_ids:
        Colaborador.objects.filter(pk__in=freelancer_collaborator_ids).update(
            categoria_trabalho='freelancer'
        )

    benefit_sheets = [
        name
        for name in reader.sheets
        if (
            normalizar_texto(name) == 'AJUDA DE CUSTO GERAL'
            or normalizar_texto(name).startswith('VT ')
            or normalizar_texto(name).startswith('VALE TRANSPORTE')
        )
    ]
    benefits_to_create = []
    benefit_weeks = []
    for benefit_sheet in benefit_sheets:
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
                benefit = BeneficioFiscal(
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
                benefits_to_create.append(benefit)
                benefit_weeks.append((benefit, weeks))
                total_issues += len(issues)
        else:
            folha.observacoes_importacao += f'Aba {benefit_sheet}: cabeçalho não encontrado.\n'
            total_issues += 1
    if benefits_to_create:
        BeneficioFiscal.objects.bulk_create(benefits_to_create, batch_size=200)
        ParcelaBeneficioFiscal.objects.bulk_create([
                ParcelaBeneficioFiscal(
                    beneficio=benefit,
                    folha=folha,
                    semana=week,
                    valor=value,
                )
                for benefit, weeks in benefit_weeks
                for week, value in enumerate(weeks, start=1)
            ], batch_size=400)

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
    skipped = 0
    type_by_regime = {
        'clt': 'salario',
        'pj': 'prestacao_servico',
        'freelancer': 'freelancer',
        'supervisor': 'prestacao_servico',
        'administrativo': 'salario',
        'rescisao': 'distrato',
    }
    transaction_prefix = f'fiscal:{folha.pk}:'
    existing_payments = {
        payment.identificador_transacao: payment
        for payment in PagamentoColaborador.objects.filter(
            identificador_transacao__startswith=transaction_prefix
        )
    }
    payments_to_create = []
    item_links = []
    installment_links = []
    invalid_items = []
    invalid_benefits = {}
    pagamentos_reutilizados = set()
    chaves_novas = set()
    colaboradores_com_folha_principal = set(
        folha.itens.filter(
            regime__in=['clt', 'pj', 'supervisor', 'administrativo']
        ).exclude(colaborador_id=None).values_list('colaborador_id', flat=True)
    )

    def chave_pagamento(payment):
        payment.normalizar_datas_semanais()
        return (
            payment.colaborador_id,
            payment.tipo,
            payment.competencia,
            payment.data_vencimento,
            payment.valor,
        )

    def pagamento_compativel(**filtros):
        candidatos = PagamentoColaborador.objects.filter(
            item_fiscal__isnull=True,
            parcela_fiscal__isnull=True,
            **filtros,
        ).exclude(pk__in=pagamentos_reutilizados).order_by('pk')
        pagamento = candidatos.first()
        if pagamento:
            pagamentos_reutilizados.add(pagamento.pk)
        return pagamento

    for item in folha.itens.select_related('colaborador', 'pagamento'):
        value = item.valor_para_pagamento
        if item.pagamento_id or not item.colaborador_id or item.problemas or not value or value <= 0:
            skipped += 1
            continue
        if (
            item.regime == 'freelancer'
            and item.colaborador_id in colaboradores_com_folha_principal
        ):
            item.problemas = [
                *item.problemas,
                'Pessoa também consta na folha principal; lançamento freelancer não gerado.',
            ]
            item.status_conciliacao = 'revisar'
            invalid_items.append(item)
            skipped += 1
            continue
        transaction_id = f'fiscal:{folha.pk}:item:{item.pk}'
        payment = existing_payments.get(transaction_id)
        if not payment:
            tipo_pagamento = type_by_regime[item.regime]
            filtros_existente = {
                'colaborador': item.colaborador,
                'tipo': tipo_pagamento,
                'valor': value,
                'status': 'pago' if item.status_fonte == 'pago' else 'pendente',
            }
            if item.status_fonte == 'pago' and item.data_pagamento_fonte:
                filtros_existente['data_pagamento'] = item.data_pagamento_fonte
            else:
                filtros_existente['competencia'] = folha.competencia
                filtros_existente['data_vencimento'] = _month_end(folha.competencia)
            payment = pagamento_compativel(**filtros_existente)
            if not payment:
                # Uma importação posterior pode trazer como pendente um valor
                # que já foi efetivamente pago em outra data. Nesse caso o
                # pagamento existente deve ser conciliado, não recriado.
                payment = pagamento_compativel(
                    colaborador=item.colaborador,
                    tipo=tipo_pagamento,
                    competencia=folha.competencia,
                    valor=value,
                )
        if not payment:
            payment = PagamentoColaborador(
                identificador_transacao=transaction_id,
                colaborador=item.colaborador,
                tipo=type_by_regime[item.regime],
                competencia=folha.competencia,
                competencia_fim=_month_end(folha.competencia),
                valor=value,
                dias_trabalhados=(
                    item.dias_trabalhados if item.regime == 'freelancer' else None
                ),
                valor_diaria=(item.valor_dia if item.regime == 'freelancer' else None),
                chave_pix=item.pix,
                data_vencimento=item.data_pagamento_fonte or _month_end(folha.competencia),
                status='pago' if item.status_fonte == 'pago' else 'pendente',
                data_pagamento=item.data_pagamento_fonte,
                observacao=f'Importado da folha Fiscal {folha.competencia:%m/%Y}, aba {item.aba_origem}, linha {item.linha_origem}.',
                criado_por=usuario,
            )
            try:
                payment.full_clean(validate_unique=False, validate_constraints=False)
            except ValidationError as exc:
                item.problemas = [*item.problemas, *exc.messages]
                item.status_conciliacao = 'revisar'
                invalid_items.append(item)
                skipped += 1
                continue
            chave = chave_pagamento(payment)
            if chave in chaves_novas:
                item.problemas = [
                    *item.problemas,
                    'Lançamento duplicado para a mesma pessoa, data, tipo e valor.',
                ]
                item.status_conciliacao = 'revisar'
                invalid_items.append(item)
                skipped += 1
                continue
            chaves_novas.add(chave)
            payments_to_create.append(payment)
            existing_payments[transaction_id] = payment
        elif payment.pk:
            campos_atualizados = []
            if (
                item.regime == 'freelancer'
                and payment.dias_trabalhados is None
                and item.dias_trabalhados is not None
            ):
                payment.dias_trabalhados = item.dias_trabalhados
                campos_atualizados.append('dias_trabalhados')
            if (
                item.regime == 'freelancer'
                and payment.valor_diaria is None
                and item.valor_dia is not None
            ):
                payment.valor_diaria = item.valor_dia
                campos_atualizados.append('valor_diaria')
            if not payment.chave_pix and item.pix:
                payment.chave_pix = item.pix
                campos_atualizados.append('chave_pix')
            if campos_atualizados:
                payment.save(update_fields=[*campos_atualizados, 'atualizado_em'])
        item_links.append((item, payment))

    for installment in folha.parcelas_beneficio.select_related('beneficio__colaborador', 'pagamento'):
        benefit = installment.beneficio
        if installment.pagamento_id or not benefit.colaborador_id or benefit.problemas or installment.valor <= 0:
            skipped += 1
            continue
        start = folha.competencia + timedelta(days=(installment.semana - 1) * 7)
        start = start - timedelta(days=start.weekday())
        transaction_id = f'fiscal:{folha.pk}:beneficio:{installment.pk}'
        payment = existing_payments.get(transaction_id)
        if not payment:
            payment = pagamento_compativel(
                colaborador=benefit.colaborador,
                tipo=benefit.tipo,
                valor=installment.valor,
                competencia=start,
                data_vencimento=start,
                status='pago' if benefit.status_fonte == 'pago' else 'pendente',
            )
        if not payment:
            payment = PagamentoColaborador(
                identificador_transacao=transaction_id,
                colaborador=benefit.colaborador,
                tipo=benefit.tipo,
                competencia=start,
                competencia_fim=start + timedelta(days=6),
                valor=installment.valor,
                chave_pix=benefit.pix,
                data_vencimento=start,
                status='pago' if benefit.status_fonte == 'pago' else 'pendente',
                observacao=f'Importado da folha Fiscal {folha.competencia:%m/%Y}, semana {installment.semana}.',
                criado_por=usuario,
            )
            try:
                payment.full_clean(validate_unique=False, validate_constraints=False)
            except ValidationError as exc:
                if benefit.pk not in invalid_benefits:
                    benefit.problemas = [*benefit.problemas, *exc.messages]
                    benefit.status_conciliacao = 'revisar'
                    invalid_benefits[benefit.pk] = benefit
                skipped += 1
                continue
            chave = chave_pagamento(payment)
            if chave in chaves_novas:
                if benefit.pk not in invalid_benefits:
                    benefit.problemas = [
                        *benefit.problemas,
                        'Benefício duplicado para a mesma pessoa e semana.',
                    ]
                    benefit.status_conciliacao = 'revisar'
                    invalid_benefits[benefit.pk] = benefit
                skipped += 1
                continue
            chaves_novas.add(chave)
            payments_to_create.append(payment)
            existing_payments[transaction_id] = payment
        elif payment.pk and not payment.chave_pix and benefit.pix:
            payment.chave_pix = benefit.pix
            payment.save(update_fields=['chave_pix', 'atualizado_em'])
        installment_links.append((installment, payment))

    if payments_to_create:
        PagamentoColaborador.objects.bulk_create(payments_to_create, batch_size=200)
    items_to_update = []
    for item, payment in item_links:
        item.pagamento = payment
        items_to_update.append(item)
    items_to_update.extend(invalid_items)
    if items_to_update:
        ItemFolhaFiscal.objects.bulk_update(
            items_to_update,
            ['pagamento', 'problemas', 'status_conciliacao'],
            batch_size=200,
        )
    installments_to_update = []
    for installment, payment in installment_links:
        installment.pagamento = payment
        installments_to_update.append(installment)
    if installments_to_update:
        ParcelaBeneficioFiscal.objects.bulk_update(
            installments_to_update, ['pagamento'], batch_size=400
        )
    if invalid_benefits:
        BeneficioFiscal.objects.bulk_update(
            list(invalid_benefits.values()),
            ['problemas', 'status_conciliacao'],
            batch_size=200,
        )

    has_review = (
        folha.itens.filter(status_conciliacao='revisar').exists()
        or folha.beneficios.filter(status_conciliacao='revisar').exists()
    )
    folha.status = 'revisao' if has_review else 'processada'
    folha.save(update_fields=['status', 'atualizado_em'])
    return len(payments_to_create), skipped
