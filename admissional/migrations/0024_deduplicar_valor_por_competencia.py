from django.db import migrations, models


TIPOS_FOLHA = [
    'salario',
    'vale_transporte',
    'ajuda_custo',
    'freelancer',
    'prestacao_servico',
]


def _ordem_preferencia(pagamento):
    identificador = pagamento.identificador_transacao or ''
    if pagamento.status == 'pago':
        return (0, pagamento.pk)
    return (
        1,
        0 if identificador.startswith('fiscal:') else 1,
        pagamento.pk,
    )


def retirar_valores_repetidos_na_competencia(apps, schema_editor):
    Pagamento = apps.get_model('admissional', 'PagamentoColaborador')
    ativos = Pagamento.objects.exclude(status='cancelado').filter(
        tipo__in=TIPOS_FOLHA
    )
    grupos = (
        ativos.values('colaborador_id', 'tipo', 'competencia', 'valor')
        .annotate(total=models.Count('pk'))
        .filter(total__gt=1)
    )
    for grupo in grupos.iterator():
        pagamentos = list(ativos.filter(
            colaborador_id=grupo['colaborador_id'],
            tipo=grupo['tipo'],
            competencia=grupo['competencia'],
            valor=grupo['valor'],
        ))
        pagamentos.sort(key=_ordem_preferencia)
        Pagamento.objects.filter(
            pk__in=[pagamento.pk for pagamento in pagamentos[1:]]
        ).update(status='cancelado', recorrente=False)


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('admissional', '0023_deduplicar_pagamentos_por_dia'),
    ]

    operations = [
        migrations.RunPython(
            retirar_valores_repetidos_na_competencia,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='pagamentocolaborador',
            constraint=models.UniqueConstraint(
                condition=(
                    ~models.Q(status='cancelado')
                    & models.Q(tipo__in=TIPOS_FOLHA)
                ),
                fields=('colaborador', 'tipo', 'competencia', 'valor'),
                name='admissional_um_valor_por_competencia',
            ),
        ),
    ]
