"""Regras operacionais informadas para a folha; valores sempre em Decimal."""
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError


def calcular_salario(salario, dias, faltas=0, gratificacao=0, descontos=0):
    if dias is None:
        raise ValidationError('Informe os dias do período para calcular o salário.')
    salario, dias, faltas, gratificacao, descontos = map(
        Decimal, (salario, dias, faltas, gratificacao, descontos),
    )
    if not all(v.is_finite() for v in (salario, dias, faltas, gratificacao, descontos)):
        raise ValidationError('Informe valores numéricos válidos.')
    if salario <= 0 or not 0 < dias <= 30 or not 0 <= faltas <= dias or min(gratificacao, descontos) < 0:
        raise ValidationError('Confira os valores: até 30 dias, faltas entre zero e os dias do período e valores não negativos.')
    total = (salario / Decimal(30) * (dias - faltas) + gratificacao - descontos).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    if total <= 0:
        raise ValidationError('Não há valor positivo a pagar. Confira os dias e descontos; não gere uma cobrança ao colaborador.')
    return total


def calcular_vt_antecipado(valor, jornada, previstos, faltas, diaria_anterior=None, desconto=0):
    if jornada not in range(1, 8) or not 0 <= previstos <= jornada or not 0 <= faltas <= 7:
        raise ValidationError('Confira a jornada (1 a 7 dias), os dias previstos e as faltas (0 a 7).')
    diaria = valor / Decimal(jornada) if diaria_anterior is None else diaria_anterior
    if not all(v.is_finite() for v in (valor, diaria, desconto)) or valor <= 0 or min(diaria, desconto) < 0:
        raise ValidationError('Informe valores válidos e não negativos.')
    total = (valor / Decimal(jornada) * previstos - diaria * faltas - desconto).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    if total <= 0:
        raise ValidationError('O desconto cobre todo o benefício. Confira os ajustes ou selecione Não precisa.')
    return total
