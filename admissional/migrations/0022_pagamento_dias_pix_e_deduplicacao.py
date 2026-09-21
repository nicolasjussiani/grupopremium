from datetime import timedelta

from django.db import migrations, models
import django.core.validators
from decimal import Decimal


def normalizar_e_retirar_duplicados(apps, schema_editor):
    Pagamento = apps.get_model('admissional', 'PagamentoColaborador')

    for pagamento in Pagamento.objects.filter(
        tipo__in=['vale_transporte', 'ajuda_custo']
    ).iterator():
        referencia = pagamento.competencia or pagamento.data_vencimento
        if not referencia:
            continue
        segunda = referencia - timedelta(days=referencia.weekday())
        atualizacoes = {
            'competencia': segunda,
            'competencia_fim': segunda + timedelta(days=6),
            'data_vencimento': segunda,
            'recorrente': pagamento.status != 'cancelado',
        }
        if pagamento.data_pagamento:
            atualizacoes['data_pagamento'] = (
                pagamento.data_pagamento
                - timedelta(days=pagamento.data_pagamento.weekday())
            )
        Pagamento.objects.filter(pk=pagamento.pk).update(**atualizacoes)

    grupos = (
        Pagamento.objects.exclude(status='cancelado')
        .values(
            'colaborador_id', 'tipo', 'competencia',
            'data_vencimento', 'valor',
        )
        .annotate(total=models.Count('pk'))
        .filter(total__gt=1)
    )
    for grupo in grupos.iterator():
        filtros = {
            campo: grupo[campo]
            for campo in (
                'colaborador_id', 'tipo', 'competencia',
                'data_vencimento', 'valor',
            )
        }
        pagamentos = list(Pagamento.objects.filter(**filtros).exclude(status='cancelado'))
        pagamentos.sort(key=lambda item: (
            0 if item.status == 'pago' else 1,
            0 if item.identificador_transacao else 1,
            item.pk,
        ))
        ids_retirar = [item.pk for item in pagamentos[1:]]
        if ids_retirar:
            Pagamento.objects.filter(pk__in=ids_retirar).update(
                status='cancelado',
                recorrente=False,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('admissional', '0021_alter_pagamentocolaborador_tipo_auxilio_telefonia'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagamentocolaborador',
            name='chave_pix',
            field=models.CharField(
                blank=True,
                help_text='Chave utilizada para este pagamento.',
                max_length=180,
                verbose_name='Chave PIX',
            ),
        ),
        migrations.AddField(
            model_name='pagamentocolaborador',
            name='dias_trabalhados',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Obrigatório para freelancer: quantidade de dias efetivamente trabalhados.',
                max_digits=7,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                verbose_name='Dias trabalhados',
            ),
        ),
        migrations.AddField(
            model_name='pagamentocolaborador',
            name='valor_diaria',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Obrigatório para freelancer. O total será dias trabalhados × diária.',
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                verbose_name='Valor da diária',
            ),
        ),
        migrations.AlterField(
            model_name='pagamentocolaborador',
            name='status',
            field=models.CharField(
                choices=[
                    ('pendente', 'Pendente'),
                    ('pago', 'Pago'),
                    ('cancelado', 'Cancelado / retirado da folha'),
                ],
                default='pendente',
                max_length=10,
            ),
        ),
        migrations.RunPython(
            normalizar_e_retirar_duplicados,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='pagamentocolaborador',
            constraint=models.UniqueConstraint(
                condition=~models.Q(status='cancelado'),
                fields=(
                    'colaborador', 'tipo', 'competencia',
                    'data_vencimento', 'valor',
                ),
                name='admissional_pagamento_ativo_sem_duplicidade',
            ),
        ),
    ]
