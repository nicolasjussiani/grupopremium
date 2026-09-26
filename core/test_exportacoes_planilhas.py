from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador, PresencaDiaria, ProgramacaoVT
from core.models import ArquivoImportado
from fiscal.models import FolhaFiscal

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def ler_aba(content, numero):
    with ZipFile(BytesIO(content)) as z:
        strings = [''.join(i.itertext()) for i in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        xml = ET.fromstring(z.read(f'xl/worksheets/sheet{numero}.xml'))
        cells = {}
        for c in xml.findall('.//s:sheetData/s:row/s:c', NS):
            v = c.find('s:v', NS)
            if v is not None:
                cells[c.attrib['r']] = strings[int(v.text)] if c.attrib.get('t') == 's' else Decimal(v.text)
        return cells, xml


class ExportacoesPlanilhaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('exportador', password='only-for-test')
        cls.pessoa = Colaborador.objects.create(nome='Ána Exemplo', unidade='Centro', vale_transporte_semanal=140)
        cls.pj = Colaborador.objects.create(nome='Beatriz', unidade='Outra', tipo_contrato='pj', ajuda_custo_semanal=210)
        cls.pago = PagamentoColaborador.objects.create(
            colaborador=cls.pessoa, tipo='vale_transporte', competencia=date(2026, 9, 28),
            data_vencimento=date(2026, 9, 28), valor=100, status='pago',
        )
        ProgramacaoVT.objects.create(colaborador=cls.pessoa, segunda=date(2026, 9, 28), pagar=True,
                                    valor_semana_completa=140, dias_presentes=5)
        PresencaDiaria.objects.create(colaborador=cls.pessoa, data=date(2026, 9, 21), status='presente')
        cls.arquivo = ArquivoImportado.objects.create(categoria='planilha', nome_original='fonte.xlsx', sha256='a'*64)
        cls.folha = FolhaFiscal.objects.create(competencia=date(2026, 9, 1), titulo='Setembro',
                                              arquivo_origem=cls.arquivo, hash_origem='b'*64)
        cls.item = cls.folha.itens.create(aba_origem='CLT', linha_origem=2, regime='clt', nome_fonte='Ána Exemplo',
                                         colaborador=cls.pessoa, valor_executar=1000, cpf_cnpj_fonte='00123456789')
        cls.beneficio = cls.folha.beneficios.create(aba_origem='VT', linha_origem=2, nome_fonte='Ána Exemplo',
                                                   colaborador=cls.pessoa, tipo='vale_transporte')
        cls.folha.parcelas_beneficio.create(beneficio=cls.beneficio, semana=1, valor=140, pagamento=cls.pago)

    def setUp(self):
        self.client.force_login(self.user)

    def test_vt_exporta_valores_salvos_e_simulacao_sem_misturar(self):
        response = self.client.get(reverse('exportar_vt_xlsx'), {'segunda': '2026-09-28'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('.xlsx', response['Content-Disposition'])
        cells, xml = ler_aba(response.content, 2)
        row = next(k[1:] for k, v in cells.items() if k.startswith('B') and v == 'Ána Exemplo')
        other = next(k[1:] for k, v in cells.items() if k.startswith('B') and v == 'Beatriz')
        self.assertEqual(cells['J'+row], 140)
        self.assertEqual(cells['M'+row], 20)  # cálculo atual, uma presença
        self.assertEqual(cells['N'+row], 100)  # pago, cinco presenças salvas
        self.assertEqual(cells['P'+row], 5)
        self.assertNotIn('K'+other, cells)  # sem presenças informadas não vira zero
        self.assertIsNotNone(xml.find('s:autoFilter', NS))
        with ZipFile(BytesIO(response.content)) as z:
            charts = [n for n in z.namelist() if n.startswith('xl/charts/chart') and n.endswith('.xml')]
            self.assertEqual(len(charts), 2)
        self.assertEqual(PagamentoColaborador.objects.count(), 1)

    def test_vt_filtra_busca_sem_acento_situacao_beneficio_e_unidade(self):
        params = {'segunda': '2026-09-28', 'busca_lista': 'ana', 'situacao': 'pago',
                  'beneficio': 'vale_transporte', 'unidade': 'Centro'}
        cells, _ = ler_aba(self.client.get(reverse('exportar_vt_xlsx'), params).content, 2)
        self.assertEqual(cells['B2'], 'Ána Exemplo')
        self.assertNotIn('B3', cells)
        params['beneficio'] = 'ajuda_custo'
        cells, _ = ler_aba(self.client.get(reverse('exportar_vt_xlsx'), params).content, 2)
        self.assertNotIn('B2', cells)

    def test_vt_rejeita_datas_filtros_e_post(self):
        for params in ({}, {'segunda':'2026-09-29'}, {'segunda':'x'},
                       {'segunda':'2026-09-28','colaborador':'x'}, {'segunda':'2026-09-28','situacao':'x'}):
            self.assertEqual(self.client.get(reverse('exportar_vt_xlsx'), params).status_code, 400)
        self.assertEqual(self.client.post(reverse('exportar_vt_xlsx')).status_code, 405)

    def test_fiscal_preserva_documentos_textuais_e_nao_executa_formulas(self):
        self.item.nome_fonte = '=HYPERLINK("https://example.com","abrir")'
        self.item.save()
        response = self.client.get(reverse('exportar_folha_fiscal_xlsx', args=[self.folha.pk]))
        cells, xml = ler_aba(response.content, 2)
        self.assertEqual(cells['B2'], self.item.nome_fonte)
        self.assertEqual(cells['C2'], '00123456789')
        self.assertEqual(cells['N2'], 1000)
        self.assertFalse(xml.findall('.//s:f', NS))
        beneficios, _ = ler_aba(response.content, 3)
        self.assertEqual(beneficios['G2'], 140)
        self.assertEqual(beneficios['K2'], 100)
        self.assertEqual(beneficios['J2'], 'Pago')

    def test_fiscal_mesmo_escopo_da_tela_preserva_rescisao_e_nao_conciliados(self):
        self.pessoa.status = 'inativo'
        self.pessoa.save()
        self.folha.itens.create(aba_origem='RESCISAO', linha_origem=3, nome_fonte='Rescisão',
                               regime='rescisao', colaborador=self.pessoa, valor_executar=300)
        self.folha.itens.create(aba_origem='PJ', linha_origem=4, nome_fonte='Não conciliado',
                               regime='pj', valor_executar=None)
        r = self.client.get(reverse('exportar_folha_fiscal_xlsx', args=[self.folha.pk]))
        cells, _ = ler_aba(r.content, 2)
        nomes = [v for k, v in cells.items() if k.startswith('B') and k != 'B1']
        self.assertCountEqual(nomes, ['Rescisão', 'Não conciliado'])
        beneficios, _ = ler_aba(r.content, 3)
        self.assertNotIn('B2', beneficios)
        self.assertEqual(PagamentoColaborador.objects.count(), 1)

    def test_lotes_separa_versoes_e_graficos_aparecem_na_tela(self):
        FolhaFiscal.objects.create(competencia=date(2026, 9, 1), titulo='Outra versão', versao=2,
                                   arquivo_origem=self.arquivo, hash_origem='c'*64)
        response = self.client.get(reverse('exportar_lotes_fiscal_xlsx'))
        cells, _ = ler_aba(response.content, 2)
        self.assertCountEqual([cells['C2'], cells['C3']], [1, 2])
        for name, args in [('painel_fiscal', []), ('detalhe_folha_fiscal', [self.folha.pk])]:
            self.assertContains(self.client.get(reverse(name, args=args)), 'report-charts')
        self.assertContains(self.client.get(reverse('programacao_vt'), {'segunda':'2026-09-28'}), 'Exportar Excel com gráficos')

    def test_exportacoes_exigem_mesmas_permissoes_das_telas(self):
        urls = [reverse('exportar_vt_xlsx')+'?segunda=2026-09-28', reverse('exportar_lotes_fiscal_xlsx'),
                reverse('exportar_folha_fiscal_xlsx', args=[self.folha.pk])]
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        leitor = User.objects.create_user('sem_permissao')
        self.client.force_login(leitor)
        for url in urls:
            self.assertRedirects(self.client.get(url), reverse('dashboard'), fetch_redirect_response=False)
        leitor.user_permissions.add(Permission.objects.get(codename='view_documentofinanceiro'))
        for url in urls[1:]:
            self.assertEqual(self.client.get(url).status_code, 403)
        leitor.user_permissions.add(Permission.objects.get(codename='view_folhafiscal'))
        for url in urls[1:]:
            self.assertEqual(self.client.get(url).status_code, 200)
