from django.db import migrations, models


def normalizar_dados(apps, schema_editor):
    Material = apps.get_model('compras', 'Material')
    Solicitacao = apps.get_model('compras', 'SolicitacaoMaterial')
    Pedido = apps.get_model('compras', 'PedidoCompra')
    Material.objects.filter(quantidade_estoque__lt=0).update(quantidade_estoque=0)
    Material.objects.filter(estoque_minimo__lt=0).update(estoque_minimo=0)
    Solicitacao.objects.filter(quantidade_solicitada__lt=0).update(quantidade_solicitada=0)
    Pedido.objects.filter(valor_unitario__lt=0).update(valor_unitario=0)
    Pedido.objects.filter(valor_total__lt=0).update(valor_total=0)


class Migration(migrations.Migration):
    dependencies = [
        ('compras', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(normalizar_dados, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='material',
            constraint=models.CheckConstraint(check=models.Q(quantidade_estoque__gte=0), name='compras_estoque_nao_negativo'),
        ),
        migrations.AddConstraint(
            model_name='material',
            constraint=models.CheckConstraint(check=models.Q(estoque_minimo__gte=0), name='compras_estoque_minimo_nao_negativo'),
        ),
        migrations.AddConstraint(
            model_name='solicitacaomaterial',
            constraint=models.CheckConstraint(check=models.Q(quantidade_solicitada__gte=0), name='compras_quantidade_solicitada_nao_negativa'),
        ),
        migrations.AddConstraint(
            model_name='pedidocompra',
            constraint=models.CheckConstraint(check=models.Q(valor_unitario__gte=0), name='compras_valor_unitario_nao_negativo'),
        ),
        migrations.AddConstraint(
            model_name='pedidocompra',
            constraint=models.CheckConstraint(check=models.Q(valor_total__gte=0), name='compras_valor_total_nao_negativo'),
        ),
    ]
