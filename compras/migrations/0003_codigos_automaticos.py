from django.db import migrations, models


def preencher_pedidos(apps, schema_editor):
    PedidoCompra = apps.get_model('compras', 'PedidoCompra')
    for pedido in PedidoCompra.objects.filter(numero_pedido='').only('pk'):
        PedidoCompra.objects.filter(pk=pedido.pk).update(numero_pedido=f'PC-{pedido.pk:06d}')


class Migration(migrations.Migration):
    dependencies = [('compras', '0002_integridade_estoque_valores')]

    operations = [
        migrations.AlterField(
            model_name='material',
            name='codigo',
            field=models.CharField(blank=True, max_length=20, unique=True, verbose_name='Código'),
        ),
        migrations.RunPython(preencher_pedidos, migrations.RunPython.noop),
    ]
