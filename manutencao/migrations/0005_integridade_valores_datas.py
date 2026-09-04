from django.db import migrations, models


def normalizar_valores(apps, schema_editor):
    Ativo = apps.get_model('manutencao', 'Ativo')
    Registro = apps.get_model('manutencao', 'RegistroManutencao')

    Ativo.objects.filter(valor_aquisicao__lt=0).update(valor_aquisicao=0)
    Registro.objects.filter(custo_reparo__lt=0).update(custo_reparo=0)
    for registro in Registro.objects.filter(data_conclusao__lt=models.F('data_inicio')).iterator():
        registro.data_conclusao = registro.data_inicio
        registro.save(update_fields=['data_conclusao'])


class Migration(migrations.Migration):

    dependencies = [
        ('manutencao', '0004_ativo_marca_ativo_modelo_ativo_numero_serie'),
    ]

    operations = [
        migrations.RunPython(normalizar_valores, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='ativo',
            constraint=models.CheckConstraint(
                check=models.Q(('valor_aquisicao__isnull', True), ('valor_aquisicao__gte', 0), _connector='OR'),
                name='manutencao_valor_ativo_nao_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='registromanutencao',
            constraint=models.CheckConstraint(
                check=models.Q(('custo_reparo__isnull', True), ('custo_reparo__gte', 0), _connector='OR'),
                name='manutencao_custo_nao_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='registromanutencao',
            constraint=models.CheckConstraint(
                check=models.Q(('data_conclusao__isnull', True), ('data_conclusao__gte', models.F('data_inicio')), _connector='OR'),
                name='manutencao_conclusao_apos_inicio',
            ),
        ),
    ]
