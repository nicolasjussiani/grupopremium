from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissional', '0019_normalizar_beneficios_segunda_feira'),
    ]

    operations = [
        migrations.AddField(
            model_name='colaborador',
            name='data_desligamento',
            field=models.DateField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name='Data de Desligamento',
            ),
        ),
    ]
