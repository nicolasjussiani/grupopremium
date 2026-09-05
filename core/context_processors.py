"""Flags leves usadas para segmentar a navegacao do ERP."""


def navigation_access(request):
    # Calculado pelo middleware antes de qualquer transacao da view. Assim o
    # template continua renderizando mesmo quando uma gravacao entra em rollback.
    return {'is_intermediario': getattr(request, 'is_intermediario', False)}
