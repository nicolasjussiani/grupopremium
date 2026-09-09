from django.db import migrations, models


def preencher_codigos(apps, schema_editor):
    Equipamento = apps.get_model('sesmet', 'EquipamentoProtecao')
    for equipamento in Equipamento.objects.filter(codigo__isnull=True).only('pk'):
        Equipamento.objects.filter(pk=equipamento.pk).update(codigo=f'EPI-{equipamento.pk:06d}')


class Migration(migrations.Migration):
    dependencies = [('sesmet', '0004_estoque_constraints')]

    operations = [
        migrations.AddField(
            model_name='equipamentoprotecao',
            name='codigo',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True, verbose_name='Código interno'),
        ),
        migrations.RunPython(preencher_codigos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='equipamentoprotecao',
            name='codigo',
            field=models.CharField(blank=True, max_length=20, unique=True, verbose_name='Código interno'),
        ),
    ]
