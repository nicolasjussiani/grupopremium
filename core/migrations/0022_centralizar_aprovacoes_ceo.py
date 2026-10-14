"""Encaminha a fila existente ao CEO sem reescrever decisões anteriores."""

import json

from django.conf import settings
from django.db import migrations, transaction


def centralizar_aprovacoes(apps, schema_editor):
    banco = schema_editor.connection.alias
    Usuario = apps.get_model(settings.AUTH_USER_MODEL)
    Aprovacao = apps.get_model('core', 'AprovacaoRegistro')
    Notificacao = apps.get_model('core', 'Notificacao')
    Log = apps.get_model('core', 'LogAtividade')
    Requisicao = apps.get_model('compras', 'RequisicaoCompra')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    with transaction.atomic(using=banco):
        pendentes = Aprovacao.objects.using(banco).filter(status='pendente')
        requisicoes = Requisicao.objects.using(banco).filter(
            status__in=('aguardando_adriana', 'aguardando_ceo'),
        )
        # Uma instalação nova ainda não tem usuários nem processos a transferir.
        if not pendentes.exists() and not requisicoes.exists():
            return

        ceos = list(Usuario.objects.using(banco).filter(
            username__iexact='ceo_premium', is_active=True,
        ).order_by('pk')[:2])
        if len(ceos) != 1:
            raise RuntimeError(
                'Não foi possível centralizar as aprovações: deve existir '
                'exatamente um usuário ativo com username ceo_premium. '
                'Regularize a conta antes de executar esta migração; '
                'nenhuma pendência foi alterada.'
            )
        ceo = ceos[0]
        aprovacoes = list(pendentes.select_for_update().order_by('pk'))
        usuarios_anteriores = dict(Usuario.objects.using(banco).filter(
            pk__in=[ap.destinatario_id for ap in aprovacoes if ap.destinatario_id],
        ).values_list('pk', 'username'))

        def notificar(aprovacao, *, transferida):
            url = f'/mobile/aprovacoes/{aprovacao.pk}/'
            urls = (url, f'/aprovacoes/{aprovacao.pk}/detalhe/')
            avisos = Notificacao.objects.using(banco).filter(
                tipo='gateway', url_acao__in=urls,
            )
            # Conclui apenas chamados desta aprovação; avisos informativos e
            # gateways de outros processos continuam intactos.
            avisos.exclude(destinatario_id=ceo.pk).filter(lida=False).update(lida=True)
            aviso_ceo = avisos.filter(destinatario_id=ceo.pk).order_by('pk').first()
            if aviso_ceo:
                if transferida and aviso_ceo.lida:
                    Notificacao.objects.using(banco).filter(pk=aviso_ceo.pk).update(lida=False)
                return
            Notificacao.objects.using(banco).create(
                destinatario_id=ceo.pk,
                tipo='gateway',
                modulo=aprovacao.modulo,
                titulo=aprovacao.titulo[:200],
                mensagem='Esta solicitação aguarda a decisão do CEO.',
                url_acao=url,
            )

        def auditar(aprovacao, destinatario_anterior, nivel_anterior, *, criada=False):
            Log.objects.using(banco).create(
                usuario_id=None,
                acao=(
                    'Aprovação pendente recuperada para o CEO'
                    if criada else 'Aprovação pendente transferida para o CEO'
                ),
                modulo=aprovacao.modulo,
                url=f'/mobile/aprovacoes/{aprovacao.pk}/',
                detalhes=json.dumps({
                    'migracao': 'core.0022_centralizar_aprovacoes_ceo',
                    'aprovacao_id': aprovacao.pk,
                    'content_type_id': aprovacao.content_type_id,
                    'object_id': aprovacao.object_id,
                    'destinatario_anterior_id': destinatario_anterior,
                    'destinatario_anterior_username': usuarios_anteriores.get(destinatario_anterior),
                    'nivel_anterior': nivel_anterior,
                    'destinatario_atual_id': ceo.pk,
                    'destinatario_atual_username': ceo.username,
                    'nivel_atual': 2,
                    'registro_criado': criada,
                }, ensure_ascii=False),
            )

        for aprovacao in aprovacoes:
            anterior_id = aprovacao.destinatario_id
            nivel_anterior = aprovacao.nivel
            transferida = anterior_id != ceo.pk or nivel_anterior != 2
            if transferida:
                Aprovacao.objects.using(banco).filter(pk=aprovacao.pk).update(
                    destinatario_id=ceo.pk, nivel=2,
                )
                auditar(aprovacao, anterior_id, nivel_anterior)
            notificar(aprovacao, transferida=transferida)

        # Não deixa requisições legadas aguardando uma etapa que não existe.
        # Cada aprovação já existente é preservada, inclusive múltiplas etapas.
        requisicoes_pendentes = list(requisicoes.select_for_update().order_by('pk'))
        if requisicoes_pendentes:
            ct, _ = ContentType.objects.using(banco).get_or_create(
                app_label='compras', model='requisicaocompra',
            )
            requisicoes_com_aprovacao = {
                ap.object_id for ap in aprovacoes if ap.content_type_id == ct.pk
            }
            for requisicao in requisicoes_pendentes:
                if requisicao.pk in requisicoes_com_aprovacao:
                    continue
                aprovacao = Aprovacao.objects.using(banco).create(
                    content_type_id=ct.pk,
                    object_id=requisicao.pk,
                    modulo='compras',
                    nivel=2,
                    status='pendente',
                    destinatario_id=ceo.pk,
                    solicitado_por_id=requisicao.solicitante_usuario_id,
                    titulo=f'Requisição de compra REQ-{requisicao.pk:06d}',
                    descricao=(
                        f'Unidade de destino: {requisicao.unidade_destino}\n'
                        f'Justificativa: {requisicao.justificativa}'
                    ),
                )
                auditar(aprovacao, None, None, criada=True)
                notificar(aprovacao, transferida=True)
            requisicoes.filter(status='aguardando_adriana').update(status='aguardando_ceo')


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0021_desativar_bloqueio_ip'),
        ('compras', '0012_pedido_com_itens'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Reverter não deve devolver decisões futuras aos responsáveis antigos.
        migrations.RunPython(centralizar_aprovacoes, migrations.RunPython.noop),
    ]
