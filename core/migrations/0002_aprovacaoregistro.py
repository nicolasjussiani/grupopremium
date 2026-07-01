# Generated manually — ERP Grupo Premium — AprovacaoRegistro (Linha de Aprovação)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AprovacaoRegistro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveBigIntegerField(verbose_name='ID do Objeto')),
                ('modulo', models.CharField(
                    choices=[
                        ('recrutamento', 'Recrutamento'),
                        ('admissional', 'Admissional'),
                        ('administrativo', 'Administrativo'),
                        ('sesmet', 'SESMET'),
                        ('compras', 'Compras'),
                        ('financeiro', 'Financeiro'),
                    ],
                    default='sistema',
                    max_length=20,
                    verbose_name='Módulo',
                )),
                ('nivel', models.IntegerField(
                    choices=[(1, 'Nível 1 — Gestor / Área'), (2, 'Nível 2 — Diretoria')],
                    default=1,
                    verbose_name='Nível de Aprovação',
                )),
                ('status', models.CharField(
                    choices=[
                        ('pendente', 'Pendente'),
                        ('aprovado', 'Aprovado'),
                        ('rejeitado', 'Rejeitado'),
                        ('cancelado', 'Cancelado'),
                    ],
                    default='pendente',
                    max_length=20,
                )),
                ('titulo', models.CharField(max_length=255, verbose_name='Título da Solicitação')),
                ('descricao', models.TextField(blank=True, verbose_name='Descrição / Contexto')),
                ('comentario', models.TextField(blank=True, verbose_name='Comentário do Aprovador')),
                ('motivo_rejeicao', models.TextField(blank=True, verbose_name='Motivo da Rejeição')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('decidido_em', models.DateTimeField(blank=True, null=True)),
                ('content_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='contenttypes.contenttype',
                    verbose_name='Tipo de Objeto',
                )),
                ('solicitado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='aprovacoes_solicitadas',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Solicitado por',
                )),
                ('aprovado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='aprovacoes_decididas',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Decidido por',
                )),
            ],
            options={
                'verbose_name': 'Aprovação',
                'verbose_name_plural': 'Aprovações',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='aprovacaoregistro',
            index=models.Index(fields=['content_type', 'object_id'], name='core_aprova_content_idx'),
        ),
        migrations.AddIndex(
            model_name='aprovacaoregistro',
            index=models.Index(fields=['status'], name='core_aprova_status_idx'),
        ),
        migrations.AddIndex(
            model_name='aprovacaoregistro',
            index=models.Index(fields=['modulo', 'status'], name='core_aprova_modulo_idx'),
        ),
    ]
