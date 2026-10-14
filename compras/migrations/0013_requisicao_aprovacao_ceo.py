from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('compras', '0012_pedido_com_itens'),
    ]

    operations = [
        migrations.AlterField(
            model_name='requisicaocompra',
            name='status',
            field=models.CharField(
                choices=[
                    ('aguardando_adriana', 'Aguardando aprovação da Adriana'),
                    ('aguardando_ceo', 'Aguardando aprovação do CEO'),
                    ('aprovada', 'Aprovada'),
                    ('pedido', 'Pedido'),
                    ('rejeitada', 'Rejeitada'),
                ],
                default='aguardando_ceo',
                max_length=30,
            ),
        ),
    ]
