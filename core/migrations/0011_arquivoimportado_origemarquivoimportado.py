import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contenttypes', '0002_remove_content_type_name'),
        ('core', '0010_fornecedor_unidade'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArquivoImportado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('categoria', models.CharField(choices=[('pagamento_colaborador', 'Pagamento de colaborador'), ('nota_fiscal', 'Nota fiscal'), ('pedido', 'Pedido'), ('reembolso', 'Reembolso'), ('planilha', 'Planilha'), ('outro', 'Outro')], max_length=40)),
                ('subcategoria', models.CharField(blank=True, max_length=60)),
                ('nome_original', models.CharField(max_length=255)),
                ('arquivo', models.FileField(max_length=500, upload_to='arquivo_central/%Y/%m/')),
                ('sha256', models.CharField(max_length=64, unique=True)),
                ('tamanho', models.PositiveBigIntegerField(default=0)),
                ('mime_type', models.CharField(blank=True, max_length=120)),
                ('status', models.CharField(choices=[('arquivado', 'Arquivado'), ('vinculado', 'Vinculado'), ('revisar', 'Revisar'), ('erro', 'Erro')], default='arquivado', max_length=20)),
                ('motivo_revisao', models.TextField(blank=True)),
                ('metadados', models.JSONField(blank=True, default=dict)),
                ('object_id', models.PositiveBigIntegerField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.contenttype')),
                ('importado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='arquivos_importados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Arquivo importado',
                'verbose_name_plural': 'Arquivos importados',
                'ordering': ['-criado_em', '-pk'],
                'indexes': [models.Index(fields=['categoria', 'status'], name='core_arquiv_categor_dd380d_idx'), models.Index(fields=['content_type', 'object_id'], name='core_arquiv_content_3ac8b1_idx')],
            },
        ),
        migrations.CreateModel(
            name='OrigemArquivoImportado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('caminho_relativo', models.CharField(max_length=2000, unique=True)),
                ('pasta_raiz', models.CharField(blank=True, max_length=255)),
                ('modificado_em', models.DateTimeField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('arquivo_importado', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='origens', to='core.arquivoimportado')),
            ],
            options={
                'verbose_name': 'Origem de arquivo importado',
                'verbose_name_plural': 'Origens de arquivos importados',
                'ordering': ['caminho_relativo'],
            },
        ),
    ]
