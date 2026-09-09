from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0007_alter_modulos_choices')]

    operations = [
        migrations.AddField(
            model_name='perfilusuario',
            name='ultimo_acesso',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Ultima atividade'),
        ),
        migrations.AlterField(
            model_name='perfilusuario',
            name='perfil',
            field=models.CharField(
                choices=[
                    ('admin', 'Administrador'),
                    ('gestor', 'Gestor'),
                    ('rh', 'RH / Departamento Pessoal'),
                    ('financeiro', 'Financeiro / Fiscal'),
                    ('sesmet', 'SESMET / Segurança do Trabalho'),
                    ('compras', 'Compras / Almoxarifado'),
                    ('estoque_compras', 'Estoque, EPI e Compras'),
                    ('operacional', 'Operacional'),
                ],
                default='operacional',
                max_length=20,
            ),
        ),
    ]
