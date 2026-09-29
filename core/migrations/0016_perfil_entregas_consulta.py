from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0015_arquivoimportado_processamento')]
    operations = [
        migrations.AlterField(
            model_name='perfilusuario', name='perfil',
            field=models.CharField(max_length=20, default='operacional', choices=[
                ('admin', 'Administrador'), ('gestor', 'Gestor'),
                ('rh', 'RH / Departamento Pessoal'), ('financeiro', 'Financeiro / Fiscal'),
                ('sesmet', 'SESMET / Segurança do Trabalho'), ('compras', 'Compras / Almoxarifado'),
                ('estoque_compras', 'Estoque, EPI e Compras'),
                ('entregas_consulta', 'Entregas — somente consulta'), ('operacional', 'Operacional'),
            ]),
        ),
    ]
