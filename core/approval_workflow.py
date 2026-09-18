"""Fluxos nominais e sequenciais de aprovação."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import AprovacaoRegistro, Notificacao


def _usuario_ativo(username, papel):
    user = get_user_model().objects.filter(
        username__iexact=username, is_active=True
    ).first()
    if not user:
        raise ValidationError(
            f'O usuário responsável pela aprovação ({papel}) não está ativo.'
        )
    return user


def aprovadora_inicial_compras():
    return _usuario_ativo(
        getattr(settings, 'COMPRAS_APROVADOR_INICIAL_USERNAME', 'adriana'),
        'Adriana',
    )


def aprovador_final_compras():
    return _usuario_ativo(
        getattr(settings, 'COMPRAS_APROVADOR_FINAL_USERNAME', 'ceo_premium'),
        'CEO',
    )


def _notificar(aprovacao, destinatario, mensagem):
    Notificacao.objects.create(
        destinatario=destinatario,
        tipo='gateway',
        modulo='compras',
        titulo=aprovacao.titulo,
        mensagem=mensagem,
        url_acao=reverse('detalhe_aprovacao_mobile', args=[aprovacao.pk]),
    )


def criar_fluxo_compras(*, objeto, titulo, descricao, solicitado_por):
    """Cria somente a primeira etapa; o CEO entra após a decisão da Adriana."""
    adriana = aprovadora_inicial_compras()
    aprovacao = AprovacaoRegistro.criar_para(
        objeto=objeto,
        titulo=titulo,
        descricao=descricao,
        modulo='compras',
        nivel=1,
        solicitado_por=solicitado_por,
    )
    aprovacao.destinatario = adriana
    aprovacao.save(update_fields=['destinatario'])
    _notificar(
        aprovacao, adriana,
        'Uma nova solicitação de Compras aguarda sua análise antes de seguir ao CEO.',
    )
    return aprovacao


def avancar_para_ceo(aprovacao):
    """Abre o nível 2 após a aprovação nominal da Adriana."""
    if not (
        aprovacao.modulo == 'compras'
        and aprovacao.nivel == 1
        and aprovacao.destinatario_id
    ):
        return None

    ceo = aprovador_final_compras()
    proxima = AprovacaoRegistro.objects.create(
        content_type=aprovacao.content_type,
        object_id=aprovacao.object_id,
        titulo=aprovacao.titulo,
        descricao=aprovacao.descricao,
        modulo='compras',
        nivel=2,
        solicitado_por=aprovacao.solicitado_por,
        destinatario=ceo,
    )

    from compras.models import RequisicaoCompra
    objeto = aprovacao.objeto
    if isinstance(objeto, RequisicaoCompra):
        objeto.status = 'aguardando_ceo'
        objeto.save(update_fields=['status', 'atualizado_em'])

    _notificar(
        proxima, ceo,
        'Adriana aprovou esta solicitação. Ela agora aguarda a decisão final do CEO.',
    )
    return proxima
