"""Responsáveis nominais distintos para pagamentos e decisões operacionais."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction


FINALIDADE_OPERACIONAL = 'operacional'
FINALIDADE_PAGAMENTO = 'pagamento'
CONFIGURACOES_APROVADORES = {
    FINALIDADE_OPERACIONAL: 'APROVADOR_OPERACIONAL_USERNAME',
    FINALIDADE_PAGAMENTO: 'APROVADOR_PAGAMENTOS_USERNAME',
}
MODELOS_PAGAMENTO = frozenset({
    ('admissional', 'pagamentocolaborador'),
    ('financeiro', 'documentofinanceiro'),
})


def finalidade_para_content_type(content_type):
    return (
        FINALIDADE_PAGAMENTO
        if (content_type.app_label, content_type.model) in MODELOS_PAGAMENTO
        else FINALIDADE_OPERACIONAL
    )


def finalidade_para_objeto(objeto):
    meta = objeto._meta.concrete_model._meta
    return (
        FINALIDADE_PAGAMENTO
        if (meta.app_label, meta.model_name) in MODELOS_PAGAMENTO
        else FINALIDADE_OPERACIONAL
    )


def aprovador_para(finalidade, *, using=None):
    configuracao = CONFIGURACOES_APROVADORES.get(finalidade)
    if configuracao is None:
        raise ValidationError('Finalidade de aprovação inválida.')
    username = getattr(settings, configuracao, '').strip()
    if not username:
        raise ValidationError(f'O responsável por aprovações de {finalidade} não está configurado.')
    outro_username = getattr(settings, CONFIGURACOES_APROVADORES[
        FINALIDADE_OPERACIONAL if finalidade == FINALIDADE_PAGAMENTO else FINALIDADE_PAGAMENTO
    ], '').strip()
    if username == outro_username:
        raise ValidationError('Pagamentos e aprovações operacionais devem ter responsáveis diferentes.')
    usuarios = get_user_model().objects
    if using:
        usuarios = usuarios.using(using)
    candidatos = list(usuarios.filter(username=username, is_active=True).order_by('pk')[:2])
    if not candidatos:
        raise ValidationError(f'O responsável por aprovações de {finalidade} não existe ou não está ativo.')
    if len(candidatos) != 1:
        raise ValidationError(f'Deve existir exatamente um responsável ativo por aprovações de {finalidade}.')
    return candidatos[0]


def usuario_e_aprovador(user, finalidade):
    if not user.is_authenticated or not user.is_active:
        return False
    try:
        return user.pk == aprovador_para(finalidade, using=user._state.db).pk
    except ValidationError:
        return False


def usuario_tem_papel_aprovador(user):
    return any(usuario_e_aprovador(user, finalidade) for finalidade in CONFIGURACOES_APROVADORES)


def usuario_e_aprovador_central(user):
    """Compatibilidade: a antiga aprovação central agora é operacional."""
    return usuario_e_aprovador(user, FINALIDADE_OPERACIONAL)


def aprovador_central(*, using=None):
    """Compatibilidade para os fluxos operacionais existentes."""
    return aprovador_para(FINALIDADE_OPERACIONAL, using=using)


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
