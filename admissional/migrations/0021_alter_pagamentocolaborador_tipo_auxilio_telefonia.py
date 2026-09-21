from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('admissional', '0020_colaborador_data_desligamento')]

    operations = [
        migrations.AlterField(
            model_name='pagamentocolaborador',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('salario', 'Salário'),
                    ('vale_transporte', 'Vale-transporte'),
                    ('ajuda_custo', 'Ajuda de custo'),
                    ('auxilio_telefonia', 'Auxílio telefonia'),
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
