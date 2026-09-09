from django.db import migrations
from django.db.models import Q


PERMISSOES = {
    'sesmet': {
        'equipamentoprotecao': ('add', 'change', 'view'),
    },
    'compras': {
        'material': ('add', 'change', 'view'),
        'solicitacaomaterial': ('add', 'change', 'view'),
        'pedidocompra': ('add', 'view'),
    },
    'core': {
        'aprovacaoregistro': ('add', 'view'),
    },
}


def criar_grupo(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    grupo, _ = Group.objects.get_or_create(name='Estoque_EPI_Compras')
    filtro = Q(pk__in=[])
    for app_label, modelos in PERMISSOES.items():
        for model, acoes in modelos.items():
            filtro |= Q(
                content_type__app_label=app_label,
                content_type__model=model,
                codename__in=[f'{acao}_{model}' for acao in acoes],
            )
    grupo.permissions.set(Permission.objects.filter(filtro))


def remover_grupo(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Estoque_EPI_Compras').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0008_perfilusuario_ultimo_acesso_e_estoque_compras'),
        ('compras', '0003_codigos_automaticos'),
        ('sesmet', '0005_equipamento_codigo_automatico'),
    ]

    operations = [migrations.RunPython(criar_grupo, remover_grupo)]
