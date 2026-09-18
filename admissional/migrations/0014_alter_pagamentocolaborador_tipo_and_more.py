from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissional', '0013_colaborador_ajuda_custo_semanal_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pagamentocolaborador',
            name='tipo',
            field=models.CharField(choices=[('salario', 'Salário'), ('vale_transporte', 'Vale-transporte'), ('ajuda_custo', 'Ajuda de custo'), ('adiantamento', 'Adiantamento'), ('salario_beneficios', 'Salário e benefícios'), ('prestacao_servico', 'Prestação de serviços'), ('freelancer', 'Freelancer'), ('distrato', 'Distrato'), ('reembolso', 'Reembolso')], max_length=30),
        ),
        migrations.AddField(
            model_name='pagamentocolaborador',
            name='identificador_transacao',
            field=models.CharField(blank=True, max_length=160, null=True, unique=True, verbose_name='Identificador da transação'),
        ),
        migrations.RemoveConstraint(
            model_name='pagamentocolaborador',
            name='pagamento_unico_colaborador_tipo_competencia',
        ),
    ]
