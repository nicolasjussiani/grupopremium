from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0014_arquivoimportado_area_e_categorias'),
    ]

    operations = [
        migrations.AlterField(
            model_name='arquivoimportado',
            name='area',
            field=models.CharField(choices=[('rh', 'RH / Departamento Pessoal'), ('recrutamento', 'Recrutamento e Seleção'), ('financeiro', 'Financeiro'), ('fiscal', 'Fiscal'), ('compras', 'Compras'), ('sesmet', 'SESMET / Segurança do Trabalho'), ('manutencao', 'Manutenção / Patrimônio'), ('administrativo', 'Administrativo'), ('geral', 'Arquivo geral')], db_index=True, default='geral', max_length=20),
        ),
        migrations.AddField(
            model_name='arquivoimportado',
            name='data_documento',
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name='Data do documento'),
        ),
        migrations.AddField(
            model_name='arquivoimportado',
            name='texto_extraido',
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.AddField(
            model_name='arquivoimportado',
            name='processado_em',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Processado em'),
        ),
    ]
