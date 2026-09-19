from django.db import migrations, models


def migrar_dados(apps, schema_editor):
    Colaborador = apps.get_model('admissional', 'Colaborador')
    Pagamento = apps.get_model('admissional', 'PagamentoColaborador')
    Pagamento.objects.filter(competencia_fim__isnull=True).update(
        competencia_fim=models.F('competencia')
    )
    Pagamento.objects.filter(
        tipo__in=['vale_transporte', 'ajuda_custo']
    ).update(recorrente=True)
    for pagamento in Pagamento.objects.filter(tipo='adiantamento').select_related('colaborador'):
        data = pagamento.data_pagamento or pagamento.data_vencimento
        if 4 <= data.day <= 15 and pagamento.valor > 1000:
            pagamento.tipo = 'salario'
        elif data.weekday() == 0 and pagamento.valor < 200:
            pagamento.tipo = (
                'ajuda_custo'
                if pagamento.colaborador.tipo_contrato == 'pj'
                else 'vale_transporte'
            )
            pagamento.recorrente = True
        elif pagamento.colaborador.tipo_contrato == 'pj':
            pagamento.tipo = 'prestacao_servico'
        else:
            pagamento.tipo = 'salario'
        pagamento.save(update_fields=['tipo', 'recorrente'])
    ids_freelancers = Pagamento.objects.filter(
        tipo='freelancer'
    ).values_list('colaborador_id', flat=True)
    Colaborador.objects.filter(pk__in=ids_freelancers).update(
        categoria_trabalho='freelancer'
    )


class Migration(migrations.Migration):
    dependencies = [('admissional', '0015_corrigir_beneficios_por_contrato')]

    operations = [
        migrations.AddField(
            model_name='colaborador',
            name='categoria_trabalho',
            field=models.CharField(
                choices=[('fixo', 'Colaborador fixo'), ('freelancer', 'Freelancer')],
                db_index=True,
                default='fixo',
                max_length=15,
                verbose_name='Categoria de trabalho',
            ),
        ),
        migrations.AddField(
            model_name='pagamentocolaborador',
            name='competencia_fim',
            field=models.DateField(blank=True, null=True, verbose_name='Fim da competência'),
        ),
        migrations.AddField(
            model_name='pagamentocolaborador',
            name='recorrente',
            field=models.BooleanField(
                default=False,
                help_text='Cria a próxima semana automaticamente quando este pagamento for marcado como pago.',
                verbose_name='Repetir semanalmente',
            ),
        ),
        migrations.AlterField(
            model_name='pagamentocolaborador',
            name='competencia',
            field=models.DateField(verbose_name='Início da competência'),
        ),
        migrations.RunPython(migrar_dados, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='pagamentocolaborador',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('salario', 'Salário'),
                    ('vale_transporte', 'Vale-transporte'),
                    ('ajuda_custo', 'Ajuda de custo'),
                    ('salario_beneficios', 'Salário e benefícios'),
                    ('prestacao_servico', 'Prestação de serviços'),
                    ('freelancer', 'Freelancer'),
                    ('distrato', 'Distrato'),
                    ('reembolso', 'Reembolso'),
                ],
                max_length=30,
            ),
        ),
    ]
