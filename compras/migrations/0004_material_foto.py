from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('compras', '0003_codigos_automaticos'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='foto',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='materiais/fotos/',
                verbose_name='Foto do material',
            ),
        ),
    ]
