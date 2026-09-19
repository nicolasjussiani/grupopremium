from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0007_integridade_valores'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentofinanceiro',
            name='centro_custo',
            field=models.CharField(blank=True, max_length=100, verbose_name='Centro de Custo'),
        ),
        migrations.AlterField(
            model_name='documentofinanceiro',
            name='cnpj_emitente',
            field=models.CharField(blank=True, max_length=18, verbose_name='CNPJ do Emitente'),
        ),
        migrations.AlterField(
            model_name='documentofinanceiro',
            name='data_emissao',
            field=models.DateField(blank=True, null=True, verbose_name='Data de Emissão'),
        ),
        migrations.AlterField(
            model_name='documentofinanceiro',
            name='razao_social_emitente',
            field=models.CharField(blank=True, max_length=200, verbose_name='Razão Social'),
        ),
        migrations.AlterField(
            model_name='documentofinanceiro',
            name='unidade',
            field=models.CharField(blank=True, max_length=100, verbose_name='Unidade'),
        ),
    ]
