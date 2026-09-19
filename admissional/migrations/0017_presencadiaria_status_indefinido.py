from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('admissional', '0016_folha_periodo_recorrencia_freelancer')]

    operations = [
        migrations.AlterField(
            model_name='presencadiaria',
            name='status',
            field=models.CharField(
                choices=[
                    ('indefinido', 'Não definido'),
                    ('presente', 'Presente'),
                    ('falta', 'Falta'),
                    ('atestado', 'Atestado/Licença'),
                    ('folga', 'Folga'),
                ],
                default='indefinido',
                max_length=20,
            ),
        ),
    ]
