from datetime import timedelta

from django.db import migrations, models


def preparar_ciclos(apps, schema_editor):
    Equipamento = apps.get_model('sesmet', 'EquipamentoProtecao')
    Registro = apps.get_model('sesmet', 'RegistroEPI')
    Equipamento.objects.update(dias_durabilidade=90)
    Registro.objects.update(ciclo_ativo=False, nivel_alerta='')
    retiradas = Registro.objects.filter(tipo_movimentacao='retirada')
    for registro in retiradas.iterator():
        registro.data_validade = registro.data_movimentacao + timedelta(days=90)
        registro.save(update_fields=['data_validade'])
    pares = retiradas.values_list('colaborador_id', 'equipamento_id').distinct()
    for colaborador_id, equipamento_id in pares.iterator():
        mais_recente = Registro.objects.filter(
            colaborador_id=colaborador_id,
            equipamento_id=equipamento_id,
        ).order_by('-data_movimentacao', '-pk').first()
        if mais_recente and mais_recente.tipo_movimentacao == 'retirada':
            Registro.objects.filter(pk=mais_recente.pk).update(ciclo_ativo=True)


class Migration(migrations.Migration):
    # PostgreSQL precisa concluir os indices antes da atualizacao historica;
    # do contrario, eventos de gatilho pendentes impedem o CREATE INDEX.
    atomic = False
    dependencies = [('sesmet', '0006_equipamentoprotecao_foto')]

    operations = [
        migrations.AddField(
            model_name='registroepi',
            name='ciclo_ativo',
            field=models.BooleanField(
                db_index=True, default=True, verbose_name='Ciclo de 90 dias ativo'
            ),
        ),
        migrations.AddField(
            model_name='registroepi',
            name='nivel_alerta',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Sem alerta'),
                    ('proximo', 'Vencimento próximo'),
                    ('urgente', 'Vencimento urgente'),
                    ('vencido', 'Vencido'),
                ],
                default='',
                max_length=10,
                verbose_name='Último alerta enviado',
            ),
        ),
        migrations.AlterField(
            model_name='equipamentoprotecao',
            name='dias_durabilidade',
            field=models.PositiveIntegerField(default=90, verbose_name='Ciclo padrão (dias)'),
        ),
        migrations.RunPython(preparar_ciclos, migrations.RunPython.noop),
    ]
