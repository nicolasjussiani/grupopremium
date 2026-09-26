from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.access import access_required

from .forms import ImportacaoFolhaFiscalForm
from .models import FolhaFiscal
from .relatorios import dados_folha, graficos_lotes
from .services import gerar_pagamentos_fiscais, importar_folha_xlsx


ACCESS = {
    'profiles': ('financeiro', 'gestor'),
    'groups': ('Financeiro_Operador', 'Financeiro_Auditor', 'Financeiro_Aprovador'),
}


def _folhas_com_resumo():
    return FolhaFiscal.objects.annotate(
        total_itens=Count('itens', distinct=True),
        itens_revisar=Count('itens', filter=Q(itens__status_conciliacao='revisar'), distinct=True),
        quantidade_beneficios=Count('beneficios', distinct=True),
        beneficios_revisar=Count(
            'beneficios', filter=Q(beneficios__status_conciliacao='revisar'), distinct=True
        ),
    )


@access_required(permission='fiscal.view_folhafiscal', **ACCESS)
def painel_fiscal(request):
    folhas = list(_folhas_com_resumo())
    return render(request, 'fiscal/painel.html', {
        'folhas': folhas, 'graficos': graficos_lotes(folhas),
        'form': ImportacaoFolhaFiscalForm(),
    })


@access_required(permission='fiscal.add_folhafiscal', **ACCESS)
@require_POST
def importar_folha(request):
    form = ImportacaoFolhaFiscalForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            'fiscal/painel.html',
            {'folhas': _folhas_com_resumo(), 'form': form},
            status=400,
        )
    uploaded = form.cleaned_data['arquivo']
    try:
        folha, created = importar_folha_xlsx(
            content=uploaded.read(),
            filename=uploaded.name,
            competencia=form.cleaned_data['competencia'],
            usuario=request.user,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('painel_fiscal')
    if created:
        messages.success(request, 'Planilha importada. Revise as pendências antes de gerar pagamentos.')
    else:
        messages.info(request, 'Esta mesma planilha já havia sido importada; o lote existente foi aberto.')
    return redirect('detalhe_folha_fiscal', pk=folha.pk)


@access_required(permission='fiscal.view_folhafiscal', **ACCESS)
def detalhe_folha(request, pk):
    folha = get_object_or_404(FolhaFiscal, pk=pk)
    return render(request, 'fiscal/detalhe.html', dados_folha(folha))


@access_required(permission='fiscal.change_folhafiscal', **ACCESS)
@require_POST
def processar_folha(request, pk):
    folha = get_object_or_404(FolhaFiscal, pk=pk)
    created, skipped = gerar_pagamentos_fiscais(folha, usuario=request.user)
    if created:
        messages.success(request, f'{created} pagamento(s) gerado(s) e integrado(s) ao Financeiro.')
    else:
        messages.info(request, 'Nenhum pagamento novo foi gerado.')
    if skipped:
        messages.warning(request, f'{skipped} registro(s) foram ignorados por pendência, valor zero ou duplicidade.')
    return redirect('detalhe_folha_fiscal', pk=folha.pk)
