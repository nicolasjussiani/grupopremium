from collections import Counter
from decimal import Decimal

from django.db.models import Count, Q, Sum
from admissional.models import Colaborador
from core.planilhas import grafico
from .models import FolhaFiscal, ItemFolhaFiscal


def dados_folha(folha):
    itens = folha.itens.select_related('colaborador', 'pagamento').prefetch_related(
        'pagamento__arquivos_importados',
    ).exclude(Q(colaborador__status__in=Colaborador.STATUS_SEM_PAGAMENTO) & ~Q(regime='rescisao'))
    beneficios = folha.beneficios.select_related('colaborador').prefetch_related(
        'parcelas__pagamento__arquivos_importados',
    ).exclude(colaborador__status__in=Colaborador.STATUS_SEM_PAGAMENTO)
    resumo_regime = list(itens.values('regime').annotate(quantidade=Count('pk'), total=Sum('valor_executar')).order_by('regime'))
    parcelas = folha.parcelas_beneficio.exclude(beneficio__colaborador__status__in=Colaborador.STATUS_SEM_PAGAMENTO)
    total_itens = itens.aggregate(total=Sum('valor_executar'))['total'] or Decimal('0')
    total_beneficios = parcelas.aggregate(total=Sum('valor'))['total'] or Decimal('0')
    pagamentos = Counter()
    for item in itens:
        if item.pagamento and item.pagamento.status in ('pendente', 'pago'):
            pagamentos[item.pagamento.status] += item.pagamento.valor
    for beneficio in beneficios:
        for parcela in beneficio.parcelas.all():
            if parcela.pagamento and parcela.pagamento.status in ('pendente', 'pago'):
                pagamentos[parcela.pagamento.status] += parcela.pagamento.valor
    return {
        'folha': folha, 'itens': itens, 'beneficios': beneficios, 'resumo_regime': resumo_regime,
        'total_executado_atual': total_itens, 'total_beneficios_atual': total_beneficios,
        'pendencias': itens.filter(status_conciliacao='revisar').count() + beneficios.filter(status_conciliacao='revisar').count(),
        'graficos': [
            grafico('Valor da folha por regime', [(r['regime'], dict(ItemFolhaFiscal.REGIMES).get(r['regime'], r['regime']), r['total'] or 0) for r in resumo_regime], moeda=True),
            grafico('Pagamentos vinculados no sistema', [(k, nome, pagamentos[k]) for k, nome in [('pendente', 'Pendente'), ('pago', 'Pago')]], moeda=True),
        ],
    }


def graficos_lotes(folhas):
    contagem = Counter(f.status for f in folhas)
    return [grafico('Lotes por situação', [(k, nome, contagem[k]) for k, nome in FolhaFiscal.STATUS])]
