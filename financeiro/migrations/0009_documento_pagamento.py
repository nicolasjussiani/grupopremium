from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('financeiro', '0008_documentofinanceiro_campos_complementares_opcionais')]

    operations = [
        migrations.AddField(
            model_name='documentofinanceiro', name='situacao_pagamento',
            field=models.CharField(max_length=15, default='nao_informado',
                choices=[('nao_informado', 'Não informado'), ('a_pagar', 'A pagar'), ('pago', 'Pago')],
                verbose_name='Situação do pagamento'),
        ),
        migrations.AddField(
            model_name='documentofinanceiro', name='data_pagamento',
            field=models.DateField(null=True, blank=True, verbose_name='Data do pagamento'),
        ),
    ]
