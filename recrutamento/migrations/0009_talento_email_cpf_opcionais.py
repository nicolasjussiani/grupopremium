from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('recrutamento', '0008_historicovaga'),
    ]

    operations = [
        migrations.AlterField(
            model_name='talento',
            name='email',
            field=models.EmailField(
                blank=True, max_length=254, null=True, unique=True, verbose_name='E-mail',
            ),
        ),
        migrations.AlterField(
            model_name='talento',
            name='cpf_cnpj',
            field=models.CharField(
                blank=True, default='', max_length=18, verbose_name='CPF/CNPJ',
            ),
        ),
    ]
