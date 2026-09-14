from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissional', '0009_documentocolaborador'),
    ]

    operations = [
        migrations.AlterField(
            model_name='colaborador',
            name='cargo',
            field=models.CharField(blank=True, max_length=200, verbose_name='Cargo'),
        ),
        migrations.AlterField(
            model_name='colaborador',
            name='cpf',
            field=models.CharField(blank=True, max_length=18, null=True, unique=True, verbose_name='CPF/CNPJ'),
        ),
        migrations.AlterField(
            model_name='colaborador',
            name='data_admissao',
            field=models.DateField(blank=True, null=True, verbose_name='Data de Admissão'),
        ),
        migrations.AlterField(
            model_name='colaborador',
            name='nome',
            field=models.CharField(blank=True, max_length=200, verbose_name='Nome Completo'),
        ),
        migrations.AlterField(
            model_name='colaborador',
            name='unidade',
            field=models.CharField(blank=True, max_length=100, verbose_name='Unidade'),
        ),
    ]
