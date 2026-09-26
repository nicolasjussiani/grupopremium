"""Exportações Excel geradas em memória pelo servidor Python."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
import xlsxwriter


def grafico(titulo, dados, *, moeda=False, chave=''):
    maior = max((abs(valor) for _, _, valor in dados), default=0) or 1
    return {
        'titulo': titulo, 'moeda': moeda, 'chave': chave,
        'barras': [dict(chave=k, nome=nome, valor=valor, largura=round(abs(valor) / maior * 100, 2))
                   for k, nome, valor in dados],
    }


def exportar_xlsx(*, titulo, contexto, abas, graficos, nome):
    """Abas: (nome, colunas (rótulo, tipo, largura), linhas). Texto nunca é fórmula."""
    stream = BytesIO()
    with xlsxwriter.Workbook(stream, {
        'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False,
    }) as wb:
        wb.set_properties({'title': titulo, 'company': 'Grupo PremiumBR'})
        padrao = {'font_name': 'Arial', 'font_size': 10, 'valign': 'vcenter'}
        formatos = {
            'texto': wb.add_format(padrao),
            'numero': wb.add_format({**padrao, 'num_format': '#,##0.##'}),
            'moeda': wb.add_format({**padrao, 'num_format': '"R$" #,##0.00;[Red]("R$" #,##0.00)'}),
            'data': wb.add_format({**padrao, 'num_format': 'dd/mm/yyyy'}),
        }
        header = wb.add_format({**padrao, 'bold': True, 'bg_color': '#14264C', 'font_color': '#FFFFFF', 'text_wrap': True})
        title = wb.add_format({**padrao, 'bold': True, 'font_size': 15, 'font_color': '#14264C'})
        note = wb.add_format({**padrao, 'font_color': '#556070', 'text_wrap': True})
        resumo = wb.add_worksheet('Resumo')
        resumo.hide_gridlines(2)
        resumo.set_tab_color('#14264C')
        resumo.set_column('A:A', 3)
        resumo.set_column('B:B', 36)
        resumo.set_column('C:C', 22)
        resumo.set_column('D:D', 3)
        resumo.set_column('E:L', 12)
        resumo.write('B2', titulo, title)
        resumo.merge_range('B4:L5', contexto, note)
        resumo.write('B6', f'Exportado em {timezone.localtime():%d/%m/%Y %H:%M}. Dados salvos no sistema.', note)
        for i, g in enumerate(graficos):
            start = 8 + i * 18
            resumo.write(start, 1, g['titulo'], title)
            resumo.write_row(start + 2, 1, ['Categoria', 'Valor (R$)' if g['moeda'] else 'Quantidade'], header)
            for j, barra in enumerate(g['barras'], start + 3):
                resumo.write_string(j, 1, barra['nome'], formatos['texto'])
                resumo.write_number(j, 2, float(barra['valor']), formatos['moeda' if g['moeda'] else 'numero'])
            if g['barras'] and any(b['valor'] for b in g['barras']):
                chart = wb.add_chart({'type': 'bar'})
                chart.add_series({
                    'name': g['titulo'],
                    'categories': ['Resumo', start + 3, 1, start + 2 + len(g['barras']), 1],
                    'values': ['Resumo', start + 3, 2, start + 2 + len(g['barras']), 2],
                    'fill': {'color': '#274C77'}, 'border': {'none': True},
                    'data_labels': {'value': True, 'num_format': '#,##0.00' if g['moeda'] else '0'},
                })
                chart.set_title({'name': g['titulo']})
                chart.set_legend({'none': True})
                chart.set_x_axis({'name': 'Reais (R$)' if g['moeda'] else 'Quantidade'})
                chart.set_y_axis({'reverse': True})
                chart.set_size({'width': 650, 'height': 300})
                resumo.insert_chart(start, 4, chart)
            else:
                resumo.write(start + 5, 4, 'Sem valores para representar neste gráfico.', note)
        for aba, colunas, linhas in abas:
            ws = wb.add_worksheet(aba)
            ws.hide_gridlines(2)
            ws.freeze_panes(1, min(2, len(colunas)))
            ws.set_row(0, 34)
            for c, (rotulo, tipo, largura) in enumerate(colunas):
                ws.set_column(c, c, largura, formatos[tipo])
                ws.write_string(0, c, rotulo, header)
            for r, linha in enumerate(linhas, 1):
                for c, valor in enumerate(linha):
                    fmt = formatos[colunas[c][1]]
                    if valor is None:
                        ws.write_blank(r, c, None, fmt)
                    elif isinstance(valor, (datetime, date)):
                        ws.write_datetime(r, c, valor, fmt)
                    elif isinstance(valor, (Decimal, int, float)):
                        ws.write_number(r, c, float(valor), fmt)
                    else:
                        ws.write_string(r, c, str(valor), fmt)
            ws.autofilter(0, 0, len(linhas), len(colunas) - 1)
            ws.set_landscape()
            ws.fit_to_pages(1, 0)
            ws.repeat_rows(0)
    response = HttpResponse(stream.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{nome}.xlsx"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
