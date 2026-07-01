"""ERP Grupo Premium — Views do Módulo 3: Administrativo"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import DemandaAdministrativa


@login_required
def lista_demandas(request):
    demandas = DemandaAdministrativa.objects.all()
    tipo_filter = request.GET.get('tipo', '')
    status_filter = request.GET.get('status', '')
    prioridade_filter = request.GET.get('prioridade', '')

    if tipo_filter:
        demandas = demandas.filter(tipo=tipo_filter)
    if status_filter:
        demandas = demandas.filter(status=status_filter)
    if prioridade_filter:
        demandas = demandas.filter(prioridade=prioridade_filter)

    return render(request, 'administrativo/lista_demandas.html', {
        'demandas': demandas,
        'tipo_filter': tipo_filter,
        'status_filter': status_filter,
        'prioridade_filter': prioridade_filter,
        'tipos': DemandaAdministrativa.TIPOS,
        'status_choices': DemandaAdministrativa.STATUS,
        'prioridades': DemandaAdministrativa.PRIORIDADES,
        'total_abertas': DemandaAdministrativa.objects.exclude(status='arquivada').count(),
        'urgentes': DemandaAdministrativa.objects.filter(prioridade='urgente').exclude(status='arquivada').count(),
    })


@login_required
def nova_demanda(request):
    if request.method == 'POST':
        # Gateway 1: Validação de completude
        titulo = request.POST.get('titulo', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        tipo = request.POST.get('tipo', '').strip()
        requisitante = request.POST.get('requisitante', '').strip()

        if not all([titulo, descricao, tipo, requisitante]):
            messages.error(request,
                '⚠️ GATEWAY: Solicitação incompleta! Preencha todos os campos obrigatórios.')
            return render(request, 'administrativo/nova_demanda.html', {
                'post_data': request.POST,
                'tipos': DemandaAdministrativa.TIPOS,
                'prioridades': DemandaAdministrativa.PRIORIDADES,
            })

        demanda = DemandaAdministrativa(
            tipo=tipo,
            titulo=titulo,
            descricao=descricao,
            requisitante=requisitante,
            requisitante_usuario=request.user,
            prioridade=request.POST.get('prioridade', 'media'),
            status='em_triagem',
        )
        demanda.save()
        messages.success(request, f'✅ Demanda "{titulo}" registrada com sucesso!')
        return redirect('detalhe_demanda', pk=demanda.pk)

    return render(request, 'administrativo/nova_demanda.html', {
        'tipos': DemandaAdministrativa.TIPOS,
        'prioridades': DemandaAdministrativa.PRIORIDADES,
    })


@login_required
def detalhe_demanda(request, pk):
    demanda = get_object_or_404(DemandaAdministrativa, pk=pk)
    return render(request, 'administrativo/detalhe_demanda.html', {
        'demanda': demanda,
        'etapas_execucao': ['Organização', 'Controle', 'Suporte operacional', 'Avaliação de relatórios e indicadores'],
    })


@login_required
def atualizar_status_demanda(request, pk):
    """Gateway 2: Finalização ou retorno para ajuste"""
    demanda = get_object_or_404(DemandaAdministrativa, pk=pk)
    if request.method == 'POST':
        novo_status = request.POST.get('status')
        obs = request.POST.get('motivo_rejeicao', '')

        if novo_status == 'arquivada':
            demanda.concluido_em = timezone.now()
            messages.success(request, f'✅ GATEWAY: Demanda "{demanda.titulo}" arquivada e concluída!')
        elif novo_status == 'aguardando_ajuste':
            demanda.motivo_rejeicao = obs
            messages.warning(request,
                f'⚠️ GATEWAY: Demanda retornada para ajuste administrativo.')
        else:
            messages.info(request, f'Status atualizado para: {demanda.get_status_display()}')

        demanda.status = novo_status
        demanda.save()
        return redirect('detalhe_demanda', pk=pk)
