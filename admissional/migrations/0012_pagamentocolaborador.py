import decimal
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('admissional', '0011_colaborador_vale_transporte_semanal'),
    ]

    operations = [
        migrations.CreateModel(
            name='PagamentoColaborador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('salario', 'Salário'), ('vale_transporte', 'Vale-transporte')], max_length=30)),
                ('competencia', models.DateField(verbose_name='Competência/período')),
                ('valor', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(decimal.Decimal('0.01'))])),
                ('data_vencimento', models.DateField(verbose_name='Vencimento')),
                ('status', models.CharField(choices=[('pendente', 'Pendente'), ('pago', 'Pago')], default='pendente', max_length=10)),
                ('data_pagamento', models.DateField(blank=True, null=True, verbose_name='Data do pagamento')),
                ('observacao', models.TextField(blank=True, verbose_name='Observação')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('colaborador', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagamentos', to='admissional.colaborador')),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pagamentos_colaboradores_criados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Pagamento de colaborador',
                'verbose_name_plural': 'Pagamentos de colaboradores',
                'ordering': ['-competencia', '-data_vencimento', '-pk'],
                'indexes': [models.Index(fields=['status', 'data_vencimento'], name='admissional_status_5263da_idx'), models.Index(fields=['colaborador', 'competencia'], name='admissional_colabor_766cba_idx')],
                'constraints': [models.UniqueConstraint(fields=('colaborador', 'tipo', 'competencia'), name='pagamento_unico_colaborador_tipo_competencia')],
            },
        ),
    ]
