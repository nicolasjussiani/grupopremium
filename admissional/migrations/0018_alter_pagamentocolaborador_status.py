from django.db import migrations, models
from django.utils import timezone


def cancelar_pagamentos_futuros_de_inativos(apps, schema_editor):
    PagamentoColaborador = apps.get_model('admissional', 'PagamentoColaborador')
    PagamentoColaborador.objects.filter(
        colaborador__status__in=['inativo', 'desligado'],
        status='pendente',
        tipo__in=[
            'salario', 'salario_beneficios', 'vale_transporte', 'ajuda_custo',
            'prestacao_servico', 'freelancer',
        ],
        data_vencimento__gte=timezone.localdate(),
    ).update(status='cancelado', recorrente=False)


class Migration(migrations.Migration):
    dependencies = [
        ('admissional', '0017_presencadiaria_status_indefinido'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pagamentocolaborador',
            name='status',
            field=models.CharField(
                choices=[
                    ('pendente', 'Pendente'),
                    ('pago', 'Pago'),
                    ('cancelado', 'Cancelado por inativação'),
                ],
                default='pendente',
                max_length=10,
            ),
        ),
        migrations.RunPython(
            cancelar_pagamentos_futuros_de_inativos,
            migrations.RunPython.noop,
        ),
    ]
