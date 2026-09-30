from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from core.access import access_required
from compras.models import SolicitacaoMaterial


@login_required
@require_safe
@access_required(profiles=('entregas_consulta', 'admin', 'compras', 'estoque_compras', 'gestor'))
def consulta_entregas(request):
    # A aprovação da RC libera a consulta; o status informa a disponibilidade.
    itens = SolicitacaoMaterial.objects.filter(
        requisicao__status='aprovada',
    ).exclude(status='cancelado').select_related('material', 'requisicao')
    unidades = list(itens.order_by('unidade_destino').values_list('unidade_destino', flat=True).distinct())
    unidade = request.GET.get('unidade', '').strip()
    if unidade:
        itens = itens.filter(unidade_destino=unidade)
    return render(request, 'compras/consulta_entregas.html', {
        'itens': itens.order_by('unidade_destino', '-requisicao_id', 'material__nome'),
        'unidades': unidades,
        'unidade': unidade,
    })
