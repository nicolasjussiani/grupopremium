from django.db import migrations, models


def preencher_area(apps, schema_editor):
    ArquivoImportado = apps.get_model('core', 'ArquivoImportado')
    mapas = {
        'pagamento_colaborador': 'rh',
        'nota_fiscal': 'fiscal',
        'documento_financeiro': 'financeiro',
        'documento_trabalhista': 'rh',
        'pedido': 'compras',
        'reembolso': 'financeiro',
        'planilha': 'fiscal',
    }
    for categoria, area in mapas.items():
        ArquivoImportado.objects.filter(categoria=categoria).update(area=area)


class Migration(migrations.Migration):
    dependencies = [('core', '0013_insert_movida_bases')]

    operations = [
        migrations.AlterField(
            model_name='arquivoimportado',
            name='categoria',
            field=models.CharField(
                choices=[
                    ('pagamento_colaborador', 'Pagamento de colaborador'),
                    ('nota_fiscal', 'Nota fiscal'),
                    ('documento_financeiro', 'Documento financeiro'),
                    ('documento_trabalhista', 'Documento trabalhista'),
                    ('pedido', 'Pedido'),
                    ('reembolso', 'Reembolso'),
                    ('planilha', 'Planilha'),
                    ('outro', 'Outro'),
                ],
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name='arquivoimportado',
            name='area',
            field=models.CharField(
                choices=[
                    ('rh', 'RH / Departamento Pessoal'),
                    ('financeiro', 'Financeiro'),
                    ('fiscal', 'Fiscal'),
                    ('compras', 'Compras'),
                    ('administrativo', 'Administrativo'),
                    ('geral', 'Arquivo geral'),
                ],
                db_index=True,
                default='geral',
                max_length=20,
            ),
        ),
        migrations.RunPython(preencher_area, migrations.RunPython.noop),
    ]
