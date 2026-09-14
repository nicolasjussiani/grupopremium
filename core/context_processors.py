"""Flags leves usadas para segmentar a navegacao do ERP."""

from django.core.cache import cache


def navigation_access(request):
    # Calculado pelo middleware antes de qualquer transacao da view. Assim o
    # template continua renderizando mesmo quando uma gravacao entra em rollback.
    contexto = {
        'is_intermediario': getattr(request, 'is_intermediario', False),
        'is_estoque_compras': getattr(request, 'is_estoque_compras', False),
    }
    if not request.user.is_authenticated:
        return contexto

    opcoes = cache.get('cadastros_gerais_opcoes_v1')
    if opcoes is None:
        from core.models import Fornecedor, Unidade
        opcoes = {
            'fornecedores_cadastrados': list(
                Fornecedor.objects.filter(ativo=True).values('razao_social', 'cnpj')
            ),
            'unidades_cadastradas': list(
                Unidade.objects.filter(ativo=True).values_list('nome', flat=True)
            ),
        }
        cache.set('cadastros_gerais_opcoes_v1', opcoes, 300)
    contexto.update(opcoes)
    return contexto
