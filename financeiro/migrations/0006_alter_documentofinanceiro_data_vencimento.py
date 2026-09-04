from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('financeiro', '0005_itemdocumentofinanceiro'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentofinanceiro',
            name='data_vencimento',
            field=models.DateField(blank=True, null=True, verbose_name='Data de Vencimento'),
        ),
    ]
