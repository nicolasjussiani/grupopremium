"""Todas as decisões de aprovação são encaminhadas diretamente ao CEO."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction


APROVADOR_USERNAME = 'ceo_premium'


def usuario_e_aprovador_central(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.username.casefold() == APROVADOR_USERNAME
    )


def aprovador_central(*, using=None):
    usuarios = get_user_model().objects
    if using:
        usuarios = usuarios.using(using)
    candidatos = list(usuarios.filter(username__iexact=APROVADOR_USERNAME, is_active=True).order_by('pk')[:2])
    if not candidatos:
        raise ValidationError('O usuário responsável pela aprovação (ceo_premium) não está ativo.')
    if len(candidatos) != 1:
        raise ValidationError('Deve existir apenas um usuário ativo com o nome ceo_premium.')
    return candidatos[0]


@transaction.atomic
def criar_fluxo_compras(*, objeto, titulo, descricao, solicitado_por):
    """Cria uma única decisão final, inclusive ao reenviar uma requisição."""
    from compras.models import RequisicaoCompra
    from core.models import AprovacaoRegistro

    aprovacao = AprovacaoRegistro.criar_para(
        objeto=objeto,
        titulo=titulo,
        descricao=descricao,
        modulo='compras',
        nivel=2,
        solicitado_por=solicitado_por,
    )
    if isinstance(objeto, RequisicaoCompra) and objeto.status == 'aguardando_adriana':
        objeto.status = 'aguardando_ceo'
        objeto.save(update_fields=['status', 'atualizado_em'])
    return aprovacao
