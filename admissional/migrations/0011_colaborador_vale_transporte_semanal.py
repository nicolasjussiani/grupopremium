import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissional', '0010_colaborador_campos_opcionais'),
    ]

    operations = [
        migrations.AddField(
            model_name='colaborador',
            name='vale_transporte_semanal',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='Vale-transporte semanal',
            ),
        ),
        migrations.AlterField(
            model_name='colaborador',
            name='salario',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='Salário',
            ),
        ),
    ]
