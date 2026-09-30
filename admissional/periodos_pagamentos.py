"""Separação da folha atual e dos pendentes de períodos encerrados."""
from calendar import monthrange
from datetime import timedelta

from django.db.models import Q

from .models import TIPOS_PAGAMENTO_SEMANAIS


def limites_periodo_atual(hoje):
    segunda = hoje - timedelta(days=hoje.weekday())
    return segunda, segunda + timedelta(days=6), hoje.replace(day=1), hoje.replace(
        day=monthrange(hoje.year, hoje.month)[1],
    )


def no_periodo(inicio, fim):
    return (
        Q(status='pago', data_pagamento__range=(inicio, fim))
        | Q(data_pagamento__isnull=True, data_vencimento__range=(inicio, fim))
        | (~Q(status='pago') & Q(data_vencimento__range=(inicio, fim)))
    )


def pagamentos_atuais(queryset, hoje):
    segunda, domingo, mes, fim_mes = limites_periodo_atual(hoje)
    semanais = Q(tipo__in=TIPOS_PAGAMENTO_SEMANAIS)
    return queryset.filter(
        (semanais & no_periodo(segunda, domingo))
        | (~semanais & no_periodo(mes, fim_mes))
    ).exclude(status='cancelado')


def pagamentos_atrasados(queryset, hoje):
    segunda, _, mes, _ = limites_periodo_atual(hoje)
    semanais = Q(tipo__in=TIPOS_PAGAMENTO_SEMANAIS)
    return queryset.filter(status='pendente').filter(
        (semanais & Q(data_vencimento__lt=segunda))
        | (~semanais & Q(data_vencimento__lt=mes))
    )
