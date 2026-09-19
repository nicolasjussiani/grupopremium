from django.db import migrations
from django.utils import timezone


def normalizar_pagamentos_semanais_pendentes(apps, schema_editor):
    PagamentoColaborador = apps.get_model('admissional', 'PagamentoColaborador')
    pagamentos = PagamentoColaborador.objects.filter(
        tipo__in=['vale_transporte', 'ajuda_custo'],
        status='pendente',
        data_vencimento__gte=timezone.localdate(),
    )
    for pagamento in pagamentos.iterator():
        referencia = pagamento.competencia or pagamento.data_vencimento
        segunda = referencia - timezone.timedelta(days=referencia.weekday())
        PagamentoColaborador.objects.filter(pk=pagamento.pk).update(
            competencia=segunda,
            competencia_fim=segunda + timezone.timedelta(days=6),
            data_vencimento=segunda,
            recorrente=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('admissional', '0018_alter_pagamentocolaborador_status'),
    ]

    operations = [
        migrations.RunPython(
            normalizar_pagamentos_semanais_pendentes,
            migrations.RunPython.noop,
        ),
    ]
