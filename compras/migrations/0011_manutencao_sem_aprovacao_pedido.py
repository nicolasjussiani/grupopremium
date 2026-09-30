from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def remover_aprovacao_duplicada_de_pedidos(apps, schema_editor):
    Aprovacao = apps.get_model('core', 'AprovacaoRegistro')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    EquipamentoManutencao = apps.get_model('compras', 'EquipamentoManutencao')
    Material = apps.get_model('compras', 'Material')
    PedidoCompra = apps.get_model('compras', 'PedidoCompra')
    SolicitacaoMaterial = apps.get_model('compras', 'SolicitacaoMaterial')
    RequisicaoCompra = apps.get_model('compras', 'RequisicaoCompra')

    content_type = ContentType.objects.filter(
        app_label='compras', model='pedidocompra'
    ).first()
    if not content_type:
        return

    pendentes = Aprovacao.objects.filter(
        content_type_id=content_type.pk, status='pendente'
    )
    pedido_ids = set(pendentes.values_list('object_id', flat=True))
    pedido_ids.update(PedidoCompra.objects.filter(
        status='aguardando_aprovacao'
    ).values_list('pk', flat=True))
    pendentes.update(status='cancelado', decidido_em=django.utils.timezone.now())

    pedidos = PedidoCompra.objects.filter(
        pk__in=pedido_ids, status='aguardando_aprovacao'
    )
    solicitacao_ids = list(pedidos.values_list('solicitacao_id', flat=True))
    pedidos.update(status='pedido_emitido')
    SolicitacaoMaterial.objects.filter(pk__in=solicitacao_ids).update(
        status='aguardando_entrega'
    )
    requisicao_ids = list(SolicitacaoMaterial.objects.filter(
        pk__in=solicitacao_ids, requisicao_id__isnull=False
    ).values_list('requisicao_id', flat=True))
    RequisicaoCompra.objects.filter(
        pk__in=requisicao_ids, status='aprovada'
    ).update(status='pedido')

    pedidos_emitidos = PedidoCompra.objects.filter(
        status__in=(
            'pedido_emitido', 'aguardando_recebimento', 'recebido_conferencia',
            'entrada_estoque', 'concluido',
        ),
        solicitacao__requisicao_id__isnull=False,
    )
    RequisicaoCompra.objects.filter(
        pk__in=pedidos_emitidos.values_list('solicitacao__requisicao_id', flat=True),
        status='aprovada',
    ).update(status='pedido')

    material_type = ContentType.objects.filter(app_label='compras', model='material').first()
    if material_type:
        Aprovacao.objects.filter(
            content_type_id=material_type.pk, status='pendente'
        ).update(status='cancelado', decidido_em=django.utils.timezone.now())

    for material in Material.objects.filter(categoria__in=('ferramentas', 'manutencao')):
        EquipamentoManutencao.objects.create(
            nome=material.nome,
            tipo='ferramenta' if material.categoria == 'ferramentas' else 'equipamento',
            codigo=material.codigo,
            localizacao=material.localizacao,
            descricao=material.descricao,
            ativo=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('compras', '0010_insert_es_car_care_products'),
        ('core', '0017_detalhamento_e_recebimentos'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='requisicaocompra',
            name='status',
            field=models.CharField(
                choices=[
                    ('aguardando_adriana', 'Aguardando aprovação da Adriana'),
                    ('aguardando_ceo', 'Aguardando aprovação do CEO'),
                    ('aprovada', 'Aprovada'),
                    ('pedido', 'Pedido'),
                    ('rejeitada', 'Rejeitada'),
                ],
                default='aguardando_adriana', max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='pedidocompra',
            name='status',
            field=models.CharField(
                choices=[
                    ('em_cotacao', 'Em Cotação'),
                    ('aguardando_aprovacao', 'Aguardando Aprovação'),
                    ('aprovado', 'Aprovado'),
                    ('reprovado', 'Reprovado — Nova Cotação'),
                    ('pedido_emitido', 'Pedido'),
                    ('aguardando_recebimento', 'Aguardando Recebimento'),
                    ('recebido_conferencia', 'Recebido — Em Conferência'),
                    ('entrada_estoque', 'Entrada no Estoque'),
                    ('concluido', 'Concluído'),
                ],
                default='em_cotacao', max_length=30,
            ),
        ),
        migrations.CreateModel(
            name='EquipamentoManutencao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=200, verbose_name='Nome')),
                ('tipo', models.CharField(choices=[('maquina', 'Máquina'), ('ferramenta', 'Ferramenta'), ('equipamento', 'Equipamento')], default='equipamento', max_length=20)),
                ('codigo', models.CharField(blank=True, max_length=40, verbose_name='Código / patrimônio')),
                ('localizacao', models.CharField(blank=True, max_length=150, verbose_name='Unidade / localização')),
                ('descricao', models.TextField(blank=True, verbose_name='Descrição')),
                ('ativo', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Equipamento de manutenção', 'verbose_name_plural': 'Equipamentos de manutenção', 'ordering': ['nome']},
        ),
        migrations.CreateModel(
            name='SolicitacaoManutencao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('problema', models.TextField(verbose_name='Manutenção necessária')),
                ('status', models.CharField(choices=[('pendente', 'Aguardando aprovação da RC'), ('aguardando_manutencao', 'Aguardando manutenção'), ('em_manutencao', 'Em manutenção'), ('concluida', 'Concluída'), ('cancelada', 'Cancelada')], default='pendente', max_length=30)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('equipamento', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='solicitacoes', to='compras.equipamentomanutencao')),
                ('requisicao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='manutencoes', to='compras.requisicaocompra')),
            ],
            options={'verbose_name': 'Solicitação de manutenção', 'verbose_name_plural': 'Solicitações de manutenção', 'ordering': ['id']},
        ),
        migrations.RunPython(remover_aprovacao_duplicada_de_pedidos, migrations.RunPython.noop),
    ]
