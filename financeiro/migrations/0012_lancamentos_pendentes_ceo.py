from django.conf import settings
from django.db import migrations, transaction


def encaminhar_lancamentos_pendentes(apps, schema_editor):
    alias = schema_editor.connection.alias
    Lancamento = apps.get_model('financeiro', 'LancamentoERP')
    Aprovacao = apps.get_model('core', 'AprovacaoRegistro')
    Notificacao = apps.get_model('core', 'Notificacao')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    User = apps.get_model(settings.AUTH_USER_MODEL)

    with transaction.atomic(using=alias):
        pendentes = Lancamento.objects.using(alias).filter(
            status='em_validacao',
        ).exclude(documento__status='cancelado')
        if not pendentes.exists():
            return
        ceos = list(User.objects.using(alias).filter(
            username__iexact='ceo_premium', is_active=True,
        ).values_list('pk', flat=True)[:2])
        if len(ceos) != 1:
            raise RuntimeError('É necessário exatamente um usuário ceo_premium ativo para encaminhar os lançamentos pendentes.')
        content_type, _ = ContentType.objects.using(alias).get_or_create(
            app_label='financeiro', model='lancamentoerp',
        )
        vinculados = Aprovacao.objects.using(alias).filter(
            content_type_id=content_type.pk, status='pendente',
        ).values_list('object_id', flat=True)
        for lancamento in pendentes.exclude(pk__in=vinculados).iterator():
            aprovacao = Aprovacao.objects.using(alias).create(
                content_type_id=content_type.pk,
                object_id=lancamento.pk,
                modulo='financeiro', nivel=2, destinatario_id=ceos[0],
                titulo=f'Lançamento financeiro #{lancamento.pk}',
                descricao=f'{lancamento.descricao} — R$ {lancamento.valor} — {lancamento.centro_custo}',
                solicitado_por_id=lancamento.lancado_por_id,
            )
            Notificacao.objects.using(alias).create(
                destinatario_id=ceos[0], tipo='gateway', modulo='financeiro',
                titulo=aprovacao.titulo[:200],
                mensagem='Lançamento financeiro pendente encaminhado para sua aprovação direta.',
                url_acao=f'/mobile/aprovacoes/{aprovacao.pk}/',
            )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0022_centralizar_aprovacoes_ceo'),
        ('financeiro', '0011_merge_cancelamento_recebimentos'),
    ]

    operations = [
        migrations.RunPython(encaminhar_lancamentos_pendentes, migrations.RunPython.noop),
    ]
