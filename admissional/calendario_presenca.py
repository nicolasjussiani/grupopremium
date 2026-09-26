"""Resumo mensal de preenchimento, usando a mesma seleção da lista diária."""
from calendar import Calendar, monthrange
from datetime import date
from urllib.parse import urlencode

from django.db.models import Count
from django.utils import timezone

from .models import PresencaDiaria


MESES = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
         'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')


def montar_calendario_presenca(data_selecionada, mes, filtros, colaboradores):
    try:
        inicio = date.fromisoformat(f'{mes}-01')
    except (ValueError, TypeError):
        inicio = data_selecionada.replace(day=1)
    fim = inicio.replace(day=monthrange(inicio.year, inicio.month)[1])
    hoje = timezone.localdate()
    total = colaboradores.count()
    preenchidos = dict(
        PresencaDiaria.objects.filter(
            colaborador__in=colaboradores, data__range=(inicio, fim),
        ).exclude(status='indefinido').order_by().values('data')
        .annotate(total=Count('pk')).values_list('data', 'total')
    )

    def link(data, **extra):
        return '?' + urlencode({**filtros, 'data': data.isoformat(), **extra})

    semanas = []
    pendentes = completos = 0
    for semana in Calendar(firstweekday=6).monthdayscalendar(inicio.year, inicio.month):
        dias = []
        for numero in semana:
            if not numero:
                dias.append(None)
                continue
            dia = inicio.replace(day=numero)
            definidos = preenchidos.get(dia, 0)
            faltam = total - definidos
            if not total:
                estado, descricao, marcador = 'vazio', 'Sem colaboradores nos filtros', '—'
            elif dia > hoje:
                estado, descricao, marcador = 'futuro', f'Data futura · {definidos} de {total} preenchidos', '·'
            elif faltam:
                estado = 'pendente'
                descricao = f'{faltam} de {total} sem preenchimento'
                marcador = '!'
                pendentes += 1
            else:
                estado, descricao, marcador = 'completo', f'{total} de {total} preenchidos', '✓'
                completos += 1
            dias.append({
                'numero': numero, 'estado': estado, 'marcador': marcador,
                'descricao': f'{dia:%d/%m/%Y} · {descricao}',
                'url': link(dia), 'selecionado': dia == data_selecionada,
                'hoje': dia == hoje,
            })
        semanas.append(dias)

    def vizinho(deslocamento):
        indice = inicio.year * 12 + inicio.month - 1 + deslocamento
        ano, mes_zero = divmod(indice, 12)
        if not 1 <= ano <= 9999:
            return ''
        return link(data_selecionada, mes_calendario=f'{ano:04d}-{mes_zero + 1:02d}')

    return {
        'titulo': f'{MESES[inicio.month - 1]} de {inicio.year}',
        'semanas': semanas, 'pendentes': pendentes, 'completos': completos,
        'total': total, 'anterior': vizinho(-1), 'proximo': vizinho(1),
        'mes_selecionado': link(data_selecionada),
    }
