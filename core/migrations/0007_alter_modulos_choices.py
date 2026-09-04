from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_alter_perfilusuario_marca'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aprovacaoregistro',
            name='modulo',
            field=models.CharField(
                choices=[
                    ('recrutamento', 'Recrutamento'),
                    ('admissional', 'Admissional'),
                    ('administrativo', 'Administrativo'),
                    ('sesmet', 'SESMET'),
                    ('compras', 'Compras'),
                    ('financeiro', 'Financeiro'),
                    ('manutencao', 'Manutenção / Patrimônio'),
                    ('sistema', 'Sistema'),
                ],
                default='sistema',
                max_length=20,
                verbose_name='Módulo',
            ),
        ),
        migrations.AlterField(
            model_name='notificacao',
            name='modulo',
            field=models.CharField(
                choices=[
                    ('recrutamento', 'Recrutamento'),
                    ('admissional', 'Admissional'),
                    ('administrativo', 'Administrativo'),
                    ('sesmet', 'SESMET'),
                    ('compras', 'Compras'),
                    ('financeiro', 'Financeiro'),
                    ('manutencao', 'Manutenção / Patrimônio'),
                    ('sistema', 'Sistema'),
                ],
                default='sistema',
                max_length=20,
            ),
        ),
    ]
