from datetime import timedelta
from decimal import Decimal
import unicodedata

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET

from core.access import access_required
from core.planilhas import exportar_xlsx, grafico
from .programacao_vt import linhas_semana


SITUACOES = {'revisar': 'A revisar', 'pagar': 'Pendente de pagamento', 'pago': 'Pago', 'nao': 'Não recebe'}


def graficos_vt(linhas):
    return [
        grafico('Pessoas por situação', [(k, nome, sum(l['situacao'] == k for l in linhas))
                for k, nome in SITUACOES.items()], chave='pessoas'),
        grafico('Valores salvos por situação', [(k, nome, sum(
            (l['pagamento'].valor for l in linhas if l['situacao'] == k and l['pagamento']), Decimal('0'),
        )) for k, nome in [('pagar', 'Pendente'), ('pago', 'Pago')]], moeda=True, chave='valores'),
    ]


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if not unicodedata.combining(c))


@login_required
@access_required(permission='admissional.view_pagamentocolaborador', profiles=('rh', 'financeiro', 'gestor'))
@require_GET
def exportar_vt(request):
    try:
        segunda = parse_date(request.GET.get('segunda', ''))
        if segunda is None:
            raise ValueError
        if segunda.weekday() != 0 or not 1901 <= segunda.year <= 2099:
            raise ValueError
        colaborador = request.GET.get('colaborador') or None
        if colaborador is not None:
            colaborador = int(colaborador)
        if request.GET.get('situacao', 'todos') not in {'todos', *SITUACOES}:
            raise ValueError
        if request.GET.get('beneficio', 'todos') not in {'todos', 'vale_transporte', 'ajuda_custo'}:
            raise ValueError
    except (ValueError, TypeError):
        return HttpResponseBadRequest('Semana ou filtros inválidos.')
    linhas = linhas_semana(
        segunda, busca=request.GET.get('q', ''), unidade=request.GET.get('unidade', ''),
        categoria=request.GET.get('categoria', ''), colaborador_id=colaborador,
        tipo=request.GET.get('tipo', ''),
    )
    busca = normalizar(request.GET.get('busca_lista', '').strip())
    beneficio = request.GET.get('beneficio', 'todos')
    situacao = request.GET.get('situacao', 'todos')
    linhas = [l for l in linhas if
              (beneficio == 'todos' or l['tipo_beneficio'] == beneficio)
              and (situacao == 'todos' or l['situacao'] == situacao)
              and busca in normalizar(f"{l['pessoa'].nome} {l['pessoa'].unidade} {l['pessoa'].pk} {l['pessoa'].tipo_contrato} {l['nome_beneficio']}")]
    colunas = [
        ('Cadastro', 'numero', 12), ('Colaborador', 'texto', 40), ('Unidade', 'texto', 25),
        ('Contrato', 'texto', 12), ('Benefício', 'texto', 20), ('Semana do pagamento', 'data', 20),
        ('Início das presenças', 'data', 20), ('Fim das presenças', 'data', 20),
        ('Situação', 'texto', 25), ('Valor da semana completa', 'moeda', 25),
        ('Dias presentes atuais', 'numero', 20), ('Dias sem informação', 'numero', 20),
        ('Cálculo atual (não salvo)', 'moeda', 25), ('Valor do pagamento salvo', 'moeda', 26),
        ('Valor base salvo no cálculo', 'moeda', 27), ('Dias presentes salvos', 'numero', 23),
    ] + [(dia, 'texto', 20) for dia in ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')]
    dados = []
    for l in linhas:
        p, pagamento, calculo = l['pessoa'], l['pagamento'], l['calculo_salvo']
        dados.append([
            p.pk, p.nome, p.unidade, p.get_tipo_contrato_display(), l['nome_beneficio'], segunda,
            segunda - timedelta(days=7), segunda - timedelta(days=1), SITUACOES[l['situacao']],
            l['valor'], l['dias'], l['dias_pendentes'], l['valor_calculado'],
            pagamento.valor if pagamento and l['situacao'] in ('pagar', 'pago') else None,
            calculo.valor_semana_completa if calculo else None,
            calculo.dias_presentes if calculo else None,
            *[dia['descricao'] for dia in l['dias_semana']],
        ])
    filtros = ', '.join(f'{k}: {v}' for k, v in request.GET.items() if k in {
        'q', 'unidade', 'categoria', 'colaborador', 'tipo', 'busca_lista', 'beneficio', 'situacao',
    } and v)
    return exportar_xlsx(
        titulo='VT e ajuda de custo',
        contexto=f'Semana de {segunda:%d/%m/%Y}. {len(linhas)} pessoas. {filtros}\n'
                 'Gráficos de valores usam pagamentos salvos; o cálculo atual é somente uma simulação pelas presenças registradas.',
        abas=[('Colaboradores', colunas, dados)], graficos=graficos_vt(linhas), nome=f'vt-ajuda-{segunda:%Y-%m-%d}',
    )
