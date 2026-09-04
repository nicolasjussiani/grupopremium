from django.db import migrations, models


def normalizar_estoque(apps, schema_editor):
    Equipamento = apps.get_model('sesmet', 'EquipamentoProtecao')
    Registro = apps.get_model('sesmet', 'RegistroEPI')
    Equipamento.objects.filter(estoque_atual__lt=0).update(estoque_atual=0)
    Registro.objects.filter(quantidade__lte=0).update(quantidade=1)


class Migration(migrations.Migration):
    dependencies = [
        ('sesmet', '0003_equipamentoprotecao_alter_registroepi_options_and_more'),
    ]

    operations = [
        migrations.RunPython(normalizar_estoque, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='equipamentoprotecao',
            constraint=models.CheckConstraint(
                check=models.Q(estoque_atual__gte=0),
                name='sesmet_estoque_epi_nao_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='registroepi',
            constraint=models.CheckConstraint(
                check=models.Q(quantidade__gt=0),
                name='sesmet_quantidade_epi_positiva',
            ),
        ),
    ]
