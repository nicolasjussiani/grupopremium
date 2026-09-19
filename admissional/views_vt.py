from django.contrib.auth.decorators import login_required
from django.db.models import Max, Sum
from django.shortcuts import get_object_or_404, render

from core.access import access_required, user_has_access

from .models import Colaborador, PagamentoColaborador


@login_required
@access_required(
    permission='admissional.view_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
def historico_vt_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    pagamentos = (
        PagamentoColaborador.objects.filter(
            colaborador=colaborador,
            tipo='vale_transporte',
            status='pago',
        )
        .prefetch_related('arquivos_importados')
        .order_by('-data_pagamento', '-competencia', '-pk')
    )
    resumo = pagamentos.aggregate(
        total_pago=Sum('valor'),
        ultimo_pagamento=Max('data_pagamento'),
    )
    return render(request, 'admissional/historico_vt_colaborador.html', {
        'colaborador': colaborador,
        'pagamentos': pagamentos,
        'total_pago': resumo['total_pago'] or 0,
        'ultimo_pagamento': resumo['ultimo_pagamento'],
        'quantidade_pagamentos': pagamentos.count(),
        'can_add_pagamento': user_has_access(
            request.user,
            permission='admissional.add_pagamentocolaborador',
            profiles=('rh', 'financeiro', 'gestor'),
        ),
    })
