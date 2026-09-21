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
        return (0, -pagamento.valor, pagamento.pk)
    return (
        1,
        0 if identificador.startswith('fiscal:') else 1,
        -pagamento.valor,
        pagamento.pk,
    )


def retirar_duplicidades_por_dia(apps, schema_editor):
    Pagamento = apps.get_model('admissional', 'PagamentoColaborador')
    ativos = Pagamento.objects.exclude(status='cancelado').filter(
        tipo__in=TIPOS_FOLHA
    )

    grupos_mesmo_tipo = (
        ativos.values('colaborador_id', 'tipo', 'data_vencimento')
        .annotate(total=models.Count('pk'))
        .filter(total__gt=1)
    )
    for grupo in grupos_mesmo_tipo.iterator():
        pagamentos = list(
            ativos.filter(
                colaborador_id=grupo['colaborador_id'],
                tipo=grupo['tipo'],
                data_vencimento=grupo['data_vencimento'],
            )
        )
        pagamentos.sort(key=_ordem_preferencia)
        Pagamento.objects.filter(
            pk__in=[pagamento.pk for pagamento in pagamentos[1:]]
        ).update(status='cancelado', recorrente=False)

    # A data de vencimento separa corretamente as semanas recorrentes. Esta
    # segunda passada trata importações bancárias realmente repetidas no mesmo
    # dia, mesmo quando o vencimento original era diferente.
    pagos = Pagamento.objects.filter(
        status='pago',
        data_pagamento__isnull=False,
        tipo__in=TIPOS_FOLHA,
    )
    grupos_pagos = (
        pagos.values('colaborador_id', 'tipo', 'data_pagamento')
        .annotate(total=models.Count('pk'))
        .filter(total__gt=1)
    )
    for grupo in grupos_pagos.iterator():
        pagamentos = list(pagos.filter(
            colaborador_id=grupo['colaborador_id'],
            tipo=grupo['tipo'],
            data_pagamento=grupo['data_pagamento'],
        ))
        pagamentos.sort(key=_ordem_preferencia)
        Pagamento.objects.filter(
            pk__in=[pagamento.pk for pagamento in pagamentos[1:]]
        ).update(status='cancelado', recorrente=False)

    # A planilha antiga podia trazer a mesma pessoa na folha principal e na
    # aba de freelancer. Quando ambos venciam no mesmo dia, o freelancer era
    # uma duplicação do adiantamento e não um segundo pagamento independente.
    ativos = Pagamento.objects.exclude(status='cancelado').filter(
        tipo__in=TIPOS_FOLHA
    )
    grupos_pessoa_dia = (
        ativos.values('colaborador_id', 'data_vencimento')
        .annotate(total=models.Count('pk'))
        .filter(total__gt=1)
    )
    for grupo in grupos_pessoa_dia.iterator():
        pagamentos = list(ativos.filter(
            colaborador_id=grupo['colaborador_id'],
            data_vencimento=grupo['data_vencimento'],
        ))
        tipos = {pagamento.tipo for pagamento in pagamentos}
        if {'freelancer', 'prestacao_servico'} <= tipos:
            freelancers = [
                pagamento for pagamento in pagamentos
                if pagamento.tipo == 'freelancer'
            ]
            prestacoes = [
                pagamento for pagamento in pagamentos
                if pagamento.tipo == 'prestacao_servico'
            ]
            if any(pagamento.status == 'pago' for pagamento in freelancers):
                retirar = [
                    pagamento.pk for pagamento in prestacoes
                    if pagamento.status == 'pendente'
                ]
            else:
                retirar = [pagamento.pk for pagamento in freelancers]
            Pagamento.objects.filter(pk__in=retirar).update(
                status='cancelado', recorrente=False
            )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('admissional', '0022_pagamento_dias_pix_e_deduplicacao'),
    ]

    operations = [
        migrations.RunPython(
            retirar_duplicidades_por_dia,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='pagamentocolaborador',
            constraint=models.UniqueConstraint(
                condition=(
                    ~models.Q(status='cancelado')
                    & models.Q(tipo__in=TIPOS_FOLHA)
                ),
                fields=('colaborador', 'tipo', 'data_vencimento'),
                name='admissional_um_tipo_por_vencimento',
            ),
        ),
        migrations.AddConstraint(
            model_name='pagamentocolaborador',
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(status='pago', data_pagamento__isnull=False)
                    & models.Q(tipo__in=TIPOS_FOLHA)
                ),
                fields=('colaborador', 'tipo', 'data_pagamento'),
                name='admissional_um_tipo_pago_por_dia',
            ),
        ),
    ]
