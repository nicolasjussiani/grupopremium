from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sesmet', '0005_equipamento_codigo_automatico'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipamentoprotecao',
            name='foto',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='epis/fotos/',
                verbose_name='Foto do EPI',
            ),
        ),
    ]
