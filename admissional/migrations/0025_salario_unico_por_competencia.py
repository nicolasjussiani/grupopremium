from django.db import migrations, models


def separar_salarios_e_adiantamentos(apps, schema_editor):
    Pagamento = apps.get_model('admissional', 'PagamentoColaborador')
    ativos = Pagamento.objects.exclude(status='cancelado').filter(tipo='salario')
    grupos = (
        ativos.values('colaborador_id', 'competencia')
        .annotate(total=models.Count('pk'))
        .filter(total__gt=1)
    )
    for grupo in grupos.iterator():
        pagamentos = list(ativos.filter(
            colaborador_id=grupo['colaborador_id'],
            competencia=grupo['competencia'],
        ))
        pagamentos.sort(key=lambda pagamento: (
            -pagamento.valor,
            0 if pagamento.status == 'pago' else 1,
            pagamento.pk,
        ))
        for pagamento in pagamentos[1:]:
            if pagamento.status == 'pago':
                Pagamento.objects.filter(pk=pagamento.pk).update(
                    tipo='adiantamento', recorrente=False
                )
            else:
                Pagamento.objects.filter(pk=pagamento.pk).update(
                    status='cancelado', recorrente=False
                )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('admissional', '0024_deduplicar_valor_por_competencia'),
    ]

    operations = [
        migrations.RunPython(
            separar_salarios_e_adiantamentos,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='pagamentocolaborador',
            constraint=models.UniqueConstraint(
                condition=models.Q(tipo='salario') & ~models.Q(status='cancelado'),
                fields=('colaborador', 'competencia'),
                name='admissional_um_salario_por_competencia',
            ),
        ),
    ]
