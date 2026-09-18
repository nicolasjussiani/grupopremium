from django.db import migrations


def corrigir_vale_transporte_de_pj(apps, schema_editor):
    PagamentoColaborador = apps.get_model('admissional', 'PagamentoColaborador')
    PagamentoColaborador.objects.filter(
        tipo='vale_transporte',
        colaborador__tipo_contrato='pj',
    ).update(tipo='ajuda_custo')


class Migration(migrations.Migration):

    dependencies = [
        ('admissional', '0014_alter_pagamentocolaborador_tipo_and_more'),
    ]

    operations = [
        migrations.RunPython(
            corrigir_vale_transporte_de_pj,
            migrations.RunPython.noop,
        ),
    ]
