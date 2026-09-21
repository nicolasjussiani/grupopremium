import io
import zipfile
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador
from core.models import PerfilUsuario

from .models import FolhaFiscal
from .services import gerar_pagamentos_fiscais, importar_folha_xlsx


def _xlsx_cell(reference, value, style=0):
    if isinstance(value, (int, float)):
        return f'<c r="{reference}" s="{style}"><v>{value}</v></c>'
    escaped = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return f'<c r="{reference}" s="{style}" t="inlineStr"><is><t>{escaped}</t></is></c>'


def _xlsx_sheet(rows):
    xml_rows = []
    for number, cells in rows:
        xml_rows.append(f'<row r="{number}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


def build_test_workbook(salary=2000, execute=2100):
    clt_headers = [
        'COLABORADOR', 'CPF', 'CNPJ', 'PIX', 'BANCO PIX', 'BANCO ITAU',
        'CARGO', 'CONTRATO', 'UNIDADE', 'CLT', 'ADMISSÃO', 'SALARIO',
        'DIAS TRABALHADOS', 'VALOR DO DIA (R$)', 'BONIFICAÇÃO', 'FALTAS',
        'DESCONTOS', 'SALARIO A EXECUTAR', 'SALARIO PLANEJADO', 'OBSERVAÇÕES',
    ]
    clt_values = [
        'Pessoa Fiscal', '123.456.789-00', 'N/A', '12345678900', 'Banco', '',
        'Analista', 'Matriz', 'São Paulo', 'SIM', 46266, salary, 30, 66.67,
        100, 0, 0, execute, execute, '',
    ]
    benefit_headers = [
        'COLABORADOR', 'PIX', 'BASE', 'CONTRATO', 'VALOR PASSAGEM DIARIA',
        '1º SEMANA', '2º SEMANA', '3º SEMANA', '4º SEMANA', 'TOTAL GERAL',
    ]
    benefit_values = ['Pessoa Fiscal', '12345678900', 'Matriz', 'Matriz', 20, 80, 80, 80, 80, 320]

    def cells(values, row, paid=False):
        result = []
        for index, value in enumerate(values, start=1):
            letters = ''
            number = index
            while number:
                number, remainder = divmod(number - 1, 26)
                letters = chr(65 + remainder) + letters
            result.append(_xlsx_cell(f'{letters}{row}', value, 1 if paid and index == 1 else 0))
        return result

    sheet1 = _xlsx_sheet([(1, cells(clt_headers, 1)), (2, cells(clt_values, 2, paid=True))])
    sheet2 = _xlsx_sheet([(1, cells(benefit_headers, 1)), (2, cells(benefit_values, 2))])
    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''
    relationships = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="CLT" sheetId="1" r:id="rId1"/><sheet name="AJUDA DE CUSTO GERAL" sheetId="2" r:id="rId2"/></sheets></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
    styles = '''<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font/></fonts><fills count="6"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFFFFF"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFFFFF"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFFFFF"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF00B050"/></patternFill></fill></fills>
<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0"/><xf fontId="0" fillId="5" borderId="0" applyFill="1"/></cellXfs>
</styleSheet>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', relationships)
        archive.writestr('xl/workbook.xml', workbook)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        archive.writestr('xl/styles.xml', styles)
        archive.writestr('xl/worksheets/sheet1.xml', sheet1)
        archive.writestr('xl/worksheets/sheet2.xml', sheet2)
    return output.getvalue()


class FiscalIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('fiscal', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=cls.user, perfil='financeiro')
        cls.collaborator = Colaborador.objects.create(
            nome='Pessoa Fiscal',
            cpf='123.456.789-00',
            tipo_contrato='clt',
            salario='2000.00',
        )

    def _import(self):
        return importar_folha_xlsx(
            content=build_test_workbook(),
            filename='folha-fiscal.xlsx',
            competencia=date(2026, 9, 1),
            usuario=self.user,
        )

    def test_importacao_concilia_preserva_status_e_normaliza_semanas(self):
        folha, created = self._import()
        self.assertTrue(created)
        self.assertEqual(folha.status, 'pronta')
        self.assertEqual(folha.arquivo_origem.nome_original, 'folha-fiscal.xlsx')
        self.assertIn('folha-fiscal-2026-09-', folha.arquivo_origem.arquivo.name)
        self.assertEqual(folha.itens.count(), 1)
        self.assertEqual(folha.beneficios.count(), 1)
        self.assertEqual(folha.parcelas_beneficio.count(), 4)
        item = folha.itens.get()
        self.assertEqual(item.colaborador, self.collaborator)
        self.assertEqual(item.status_fonte, 'pago')
        self.assertEqual(item.status_conciliacao, 'conciliado')
        self.assertEqual(item.valor_para_pagamento, 2100)

        same, created_again = self._import()
        self.assertFalse(created_again)
        self.assertEqual(same.pk, folha.pk)
        self.assertEqual(FolhaFiscal.objects.count(), 1)

    def test_processamento_gera_pagamentos_sem_duplicar(self):
        folha, _ = self._import()
        created, skipped = gerar_pagamentos_fiscais(folha, self.user)
        self.assertEqual(created, 5)
        self.assertEqual(skipped, 0)
        self.assertEqual(PagamentoColaborador.objects.count(), 5)
        salary = PagamentoColaborador.objects.get(tipo='salario')
        self.assertEqual(salary.status, 'pago')
        self.assertEqual(salary.valor, 2100)
        self.assertEqual(salary.chave_pix, '12345678900')

        created_again, _ = gerar_pagamentos_fiscais(folha, self.user)
        self.assertEqual(created_again, 0)
        self.assertEqual(PagamentoColaborador.objects.count(), 5)

    def test_nao_gera_freelancer_quando_pessoa_tambem_esta_na_folha_principal(self):
        folha, _ = self._import()
        freelancer = folha.itens.create(
            colaborador=self.collaborator,
            aba_origem='FREELANCER',
            linha_origem=2,
            regime='freelancer',
            nome_fonte=self.collaborator.nome,
            valor_executar=Decimal('500.00'),
            status_conciliacao='conciliado',
        )

        created, skipped = gerar_pagamentos_fiscais(folha, self.user)

        self.assertEqual(created, 5)
        self.assertEqual(skipped, 1)
        self.assertFalse(
            PagamentoColaborador.objects.filter(tipo='freelancer').exists()
        )
        freelancer.refresh_from_db()
        self.assertEqual(freelancer.status_conciliacao, 'revisar')
        self.assertIn('folha principal', ' '.join(freelancer.problemas).lower())

    def test_reutiliza_valor_da_competencia_que_ja_foi_pago(self):
        existente = PagamentoColaborador.objects.create(
            colaborador=self.collaborator,
            tipo='salario',
            competencia=date(2026, 9, 1),
            competencia_fim=date(2026, 9, 30),
            valor=Decimal('2100.00'),
            data_vencimento=date(2026, 9, 10),
            status='pago',
            data_pagamento=date(2026, 9, 10),
        )
        folha, _ = self._import()
        item = folha.itens.get()
        item.status_fonte = 'pendente'
        item.data_pagamento_fonte = None
        item.save(update_fields=['status_fonte', 'data_pagamento_fonte'])

        created, skipped = gerar_pagamentos_fiscais(folha, self.user)

        self.assertEqual(created, 4)
        self.assertEqual(skipped, 0)
        self.assertEqual(PagamentoColaborador.objects.count(), 5)
        item.refresh_from_db()
        self.assertEqual(item.pagamento, existente)

    def test_salario_abaixo_de_150_e_classificado_como_freelancer(self):
        folha, _ = importar_folha_xlsx(
            content=build_test_workbook(salary=100, execute=100),
            filename='folha-freelancer.xlsx',
            competencia=date(2026, 10, 1),
            usuario=self.user,
        )
        item = folha.itens.get()
        self.assertEqual(item.regime, 'freelancer')
        self.collaborator.refresh_from_db()
        self.assertEqual(self.collaborator.categoria_trabalho, 'freelancer')
        gerar_pagamentos_fiscais(folha, self.user)
        pagamento = item.colaborador.pagamentos.get(tipo='freelancer')
        self.assertEqual(pagamento.valor, 100)
        self.assertEqual(pagamento.dias_trabalhados, 30)
        self.assertEqual(pagamento.valor_diaria, Decimal('66.67'))
        self.assertEqual(pagamento.chave_pix, '12345678900')

    def test_colaborador_inativo_vai_para_revisao_sem_abortar_lote(self):
        self.collaborator.status = 'inativo'
        self.collaborator.save(update_fields=['status'])
        folha, _ = self._import()

        created, skipped = gerar_pagamentos_fiscais(folha, self.user)

        self.assertEqual(created, 0)
        self.assertGreater(skipped, 0)
        item = folha.itens.get()
        self.assertEqual(item.status_conciliacao, 'revisar')
        self.assertIn('inativo', ' '.join(item.problemas).lower())
        benefit = folha.beneficios.get()
        self.assertEqual(benefit.status_conciliacao, 'revisar')
        self.assertIn('inativo', ' '.join(benefit.problemas).lower())

    def test_paginas_fiscais_renderizam_e_post_get_sao_separados(self):
        folha, _ = self._import()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('painel_fiscal')).status_code, 200)
        self.assertEqual(self.client.get(reverse('detalhe_folha_fiscal', args=[folha.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('importar_folha_fiscal')).status_code, 405)
        self.assertEqual(self.client.get(reverse('processar_folha_fiscal', args=[folha.pk])).status_code, 405)
