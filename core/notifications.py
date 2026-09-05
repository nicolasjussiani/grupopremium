"""Regras centralizadas de destinatarios das notificacoes internas do ERP."""

from django.contrib.auth import get_user_model
from django.db.models import Q


# Cada modulo avisa somente as equipes que trabalham diretamente nele.
# Admin_Global, superusuarios e a conta do CEO sao incluidos pela consulta abaixo.
GRUPOS_POR_MODULO = {
    'recrutamento': ('Recrutamento_Gestor', 'Recrutamento_RH'),
    'admissional': ('Admissional_RH', 'SESMET_Tecnico', 'SESMET_Gestor'),
    'administrativo': ('Administrativo_Gestor', 'Administrativo_Operador'),
    'sesmet': ('SESMET_Tecnico', 'SESMET_Gestor'),
    'compras': ('Compras_Solicitante', 'Compras_Almoxarife', 'Compras_Aprovador'),
    'financeiro': ('Financeiro_Operador', 'Financeiro_Auditor', 'Financeiro_Aprovador'),
    'manutencao': ('SESMET_Tecnico', 'SESMET_Gestor', 'Compras_Aprovador'),
}


def destinatarios_da_area(modulo, *, autor=None):
    """Retorna usuarios ativos da area e da direcao, sem repeticoes."""
    User = get_user_model()
    grupos_area = GRUPOS_POR_MODULO.get(modulo, ())
    criterio = (
        Q(is_superuser=True)
        | Q(username__iexact='ceo_premium')
        | Q(groups__name='Admin_Global')
    )
    if grupos_area:
        criterio |= Q(groups__name__in=grupos_area)

    destinatarios = User.objects.filter(criterio, is_active=True)
    if autor and getattr(autor, 'pk', None):
        destinatarios = destinatarios.exclude(pk=autor.pk)
    return destinatarios.distinct()
