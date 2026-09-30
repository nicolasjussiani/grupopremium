from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('admissional', '0028_calculo_salario_vt_antecipado')]

    operations = [
        migrations.AddField(
            model_name='colaborador', name='chave_pix',
            field=models.CharField(
                blank=True, max_length=180, verbose_name='Chave PIX',
                help_text='CPF, CNPJ, e-mail, telefone ou chave aleatÃ³ria informada pelo colaborador.',
            ),
        ),
    ]
