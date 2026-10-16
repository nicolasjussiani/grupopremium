from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0022_centralizar_aprovacoes_ceo'),
    ]

    operations = [
        migrations.AddField(
            model_name='aprovacaoregistro',
            name='finalidade',
            field=models.CharField(
                choices=[('operacional', 'Aprovação operacional'), ('pagamento', 'Autorização de pagamento')],
                db_index=True, default='operacional', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='aprovacaoregistro',
            name='dados_aprovacao',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
