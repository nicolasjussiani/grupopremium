from decimal import Decimal

from django.db import migrations, models


def normalizar_valores(apps, schema_editor):
    Documento = apps.get_model('financeiro', 'DocumentoFinanceiro')
    Lancamento = apps.get_model('financeiro', 'LancamentoERP')
    Orcamento = apps.get_model('financeiro', 'OrcamentoCentroCusto')
    Item = apps.get_model('financeiro', 'ItemDocumentoFinanceiro')

    Documento.objects.filter(valor__lte=0).update(valor=Decimal('0.01'))
    Lancamento.objects.filter(valor__lte=0).update(valor=Decimal('0.01'))
    Orcamento.objects.filter(valor_orcado__lt=0).update(valor_orcado=Decimal('0'))
    Orcamento.objects.filter(meta_reducao_custo__lt=0).update(meta_reducao_custo=Decimal('0'))
    Orcamento.objects.filter(meta_reducao_custo__gt=100).update(meta_reducao_custo=Decimal('100'))
    Item.objects.filter(quantidade__lte=0).update(quantidade=Decimal('0.001'))
    Item.objects.filter(valor_unitario__lt=0).update(valor_unitario=Decimal('0'))
    Item.objects.filter(valor_total__lt=0).update(valor_total=Decimal('0'))


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0006_alter_documentofinanceiro_data_vencimento'),
    ]

    operations = [
        migrations.RunPython(normalizar_valores, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='documentofinanceiro',
            constraint=models.CheckConstraint(
                check=models.Q(('valor__gt', 0)),
                name='financeiro_documento_valor_positivo',
            ),
        ),
        migrations.AddConstraint(
            model_name='lancamentoerp',
            constraint=models.CheckConstraint(
                check=models.Q(('valor__gt', 0)),
                name='financeiro_lancamento_valor_positivo',
            ),
        ),
        migrations.AddConstraint(
            model_name='orcamentocentrocusto',
            constraint=models.CheckConstraint(
                check=models.Q(('valor_orcado__gte', 0)),
                name='financeiro_orcamento_nao_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='orcamentocentrocusto',
            constraint=models.CheckConstraint(
                check=models.Q(('meta_reducao_custo__gte', 0), ('meta_reducao_custo__lte', 100)),
                name='financeiro_meta_percentual_valida',
            ),
        ),
        migrations.AddConstraint(
            model_name='itemdocumentofinanceiro',
            constraint=models.CheckConstraint(
                check=models.Q(('quantidade__gt', 0)),
                name='financeiro_item_quantidade_positiva',
            ),
        ),
        migrations.AddConstraint(
            model_name='itemdocumentofinanceiro',
            constraint=models.CheckConstraint(
                check=models.Q(('valor_unitario__gte', 0)),
                name='financeiro_item_unitario_nao_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='itemdocumentofinanceiro',
            constraint=models.CheckConstraint(
                check=models.Q(('valor_total__gte', 0)),
                name='financeiro_item_total_nao_negativo',
            ),
        ),
    ]
