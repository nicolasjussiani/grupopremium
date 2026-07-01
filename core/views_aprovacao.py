"""ERP Grupo Premium — Views da Linha de Aprovação"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.http import require_POST

from core.models import AprovacaoRegistro

# Mapa: grupo → módulos que ele pode aprovar
GRUPOS_APROVADORES = {
    'Recrutamento_Gestor':   ['recrutamento'],
    'Admissional_RH':        ['admissional'],
    'Administrativo_Gestor': ['administrativo'],
    'SESMET_Gestor':         ['sesmet'],
    'Compras_Aprovador':     ['compras'],
    'Financeiro_Aprovador':  ['financeiro'],
    'Admin_Global':          ['recrutamento', 'admissional', 'administrativo', 'sesmet', 'compras', 'financeiro'],
}


def _modulos_do_usuario(user):
    """Retorna a lista de módulos que o usuário pode aprovar."""
    if user.is_superuser:
        return ['recrutamento', 'admissional', 'administrativo', 'sesmet', 'compras', 'financeiro']
    modulos = set()
    grupos_usuario = user.groups.values_list('name', flat=True)
    for grupo in grupos_usuario:
        modulos.update(GRUPOS_APROVADORES.get(grupo, []))
    return list(modulos)


@login_required
def aprovacoes_pendentes(request):
    """Lista todas as aprovações pendentes para o usuário logado."""
    modulos = _modulos_do_usuario(request.user)

    aprovacoes = AprovacaoRegistro.objects.filter(
        status='pendente',
        modulo__in=modulos,
    ).select_related('content_type', 'solicitado_por').order_by('-criado_em')

    # Filtros opcionais via GET
    modulo_filtro = request.GET.get('modulo', '')
    nivel_filtro = request.GET.get('nivel', '')

    if modulo_filtro:
        aprovacoes = aprovacoes.filter(modulo=modulo_filtro)
    if nivel_filtro:
        aprovacoes = aprovacoes.filter(nivel=nivel_filtro)

    # Histórico recente (últimas 20 decididas)
    historico = AprovacaoRegistro.objects.filter(
        modulo__in=modulos,
        status__in=['aprovado', 'rejeitado'],
    ).select_related('aprovado_por').order_by('-decidido_em')[:20]

    total_pendentes = AprovacaoRegistro.objects.filter(
        status='pendente', modulo__in=modulos
    ).count()

    context = {
        'aprovacoes': aprovacoes,
        'historico': historico,
        'modulo_filtro': modulo_filtro,
        'nivel_filtro': nivel_filtro,
        'total_pendentes': total_pendentes,
        'modulos_disponiveis': modulos,
        'MODULOS_CHOICES': AprovacaoRegistro.MODULOS,
        'NIVEL_CHOICES': AprovacaoRegistro.NIVEL,
    }
    return render(request, 'core/aprovacoes_pendentes.html', context)


@login_required
@require_POST
def aprovar_registro(request, pk):
    """Aprova um registro pendente."""
    modulos = _modulos_do_usuario(request.user)
    aprovacao = get_object_or_404(
        AprovacaoRegistro, pk=pk, status='pendente', modulo__in=modulos
    )

    comentario = request.POST.get('comentario', '').strip()
    aprovacao.status = 'aprovado'
    aprovacao.aprovado_por = request.user
    aprovacao.decidido_em = timezone.now()
    aprovacao.comentario = comentario
    aprovacao.save()

    # Callback: atualiza status do objeto vinculado se ele tiver método
    _executar_callback_aprovacao(aprovacao, 'aprovado', request.user)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'mensagem': 'Registro aprovado com sucesso!'})

    messages.success(request, f'✅ "{aprovacao.titulo}" aprovado com sucesso!')
    return redirect(request.POST.get('next', 'aprovacoes_pendentes'))


@login_required
@require_POST
def rejeitar_registro(request, pk):
    """Rejeita um registro pendente."""
    modulos = _modulos_do_usuario(request.user)
    aprovacao = get_object_or_404(
        AprovacaoRegistro, pk=pk, status='pendente', modulo__in=modulos
    )

    motivo = request.POST.get('motivo_rejeicao', '').strip()
    if not motivo:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'erro', 'mensagem': 'Informe o motivo da rejeição.'}, status=400)
        messages.error(request, '❌ Informe o motivo da rejeição.')
        return redirect(request.POST.get('next', 'aprovacoes_pendentes'))

    aprovacao.status = 'rejeitado'
    aprovacao.aprovado_por = request.user
    aprovacao.decidido_em = timezone.now()
    aprovacao.motivo_rejeicao = motivo
    aprovacao.save()

    _executar_callback_aprovacao(aprovacao, 'rejeitado', request.user)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'mensagem': 'Registro rejeitado.'})

    messages.warning(request, f'🚫 "{aprovacao.titulo}" rejeitado.')
    return redirect(request.POST.get('next', 'aprovacoes_pendentes'))


@login_required
def detalhe_aprovacao(request, pk):
    """Exibe detalhes de uma aprovação (para modal ou página)."""
    modulos = _modulos_do_usuario(request.user)
    aprovacao = get_object_or_404(AprovacaoRegistro, pk=pk, modulo__in=modulos)
    return render(request, 'core/detalhe_aprovacao.html', {'aprovacao': aprovacao})


@login_required
def api_aprovacoes_pendentes_count(request):
    """API JSON: conta aprovações pendentes do usuário (para badge no menu)."""
    modulos = _modulos_do_usuario(request.user)
    total = AprovacaoRegistro.objects.filter(status='pendente', modulo__in=modulos).count()
    return JsonResponse({'total': total})


# ──────────────────────────────────────────────────────────────────────────────
# CALLBACKS POR MÓDULO
# Quando aprovação/rejeição acontece, atualiza o status do objeto vinculado.
# ──────────────────────────────────────────────────────────────────────────────

def _executar_callback_aprovacao(aprovacao, decisao, usuario):
    """
    Chama o callback correto conforme o módulo e decisão.
    Cada módulo define o que acontece quando um item é aprovado/rejeitado.
    """
    try:
        obj = aprovacao.objeto
        if obj is None:
            return

        modulo = aprovacao.modulo

        if modulo == 'recrutamento':
            _callback_recrutamento(obj, decisao, usuario)
        elif modulo == 'compras':
            _callback_compras(obj, decisao, usuario, aprovacao)
        elif modulo == 'financeiro':
            _callback_financeiro(obj, decisao, usuario, aprovacao)
        elif modulo == 'administrativo':
            _callback_administrativo(obj, decisao, usuario)
        elif modulo == 'sesmet':
            _callback_sesmet(obj, decisao, usuario)
        elif modulo == 'admissional':
            _callback_admissional(obj, decisao, usuario)

    except Exception:
        # Nunca quebra o fluxo de aprovação por erro no callback
        pass


def _callback_recrutamento(obj, decisao, usuario):
    from recrutamento.models import Vaga
    if isinstance(obj, Vaga):
        if decisao == 'aprovado':
            obj.status = 'em_selecao'
        elif decisao == 'rejeitado':
            obj.status = 'informacoes_incompletas'
        obj.save(update_fields=['status'])


def _callback_compras(obj, decisao, usuario, aprovacao):
    from compras.models import PedidoCompra
    if isinstance(obj, PedidoCompra):
        if decisao == 'aprovado':
            obj.status = 'aprovado'
            obj.aprovado_por = usuario
        elif decisao == 'rejeitado':
            obj.status = 'reprovado'
            obj.obs = aprovacao.motivo_rejeicao
        obj.save(update_fields=['status', 'aprovado_por', 'obs'] if decisao == 'aprovado' else ['status', 'obs'])


def _callback_financeiro(obj, decisao, usuario, aprovacao):
    from financeiro.models import LancamentoERP
    if isinstance(obj, LancamentoERP):
        if decisao == 'aprovado':
            obj.status = 'validado'
            obj.validado_por = usuario
        elif decisao == 'rejeitado':
            obj.status = 'rejeitado'
            obj.motivo_rejeicao = aprovacao.motivo_rejeicao
        obj.save(update_fields=['status', 'validado_por', 'motivo_rejeicao'])


def _callback_administrativo(obj, decisao, usuario):
    from administrativo.models import DemandaAdministrativa
    if isinstance(obj, DemandaAdministrativa):
        if decisao == 'aprovado':
            obj.status = 'em_execucao'
        elif decisao == 'rejeitado':
            obj.status = 'informacoes_incompletas'
        obj.save(update_fields=['status'])


def _callback_sesmet(obj, decisao, usuario):
    from sesmet.models import OrdemServico
    if isinstance(obj, OrdemServico):
        if decisao == 'aprovado':
            obj.assinado = True
            obj.data_assinatura = timezone.now().date()
        obj.save(update_fields=['assinado', 'data_assinatura'])


def _callback_admissional(obj, decisao, usuario):
    from admissional.models import Admissao
    if isinstance(obj, Admissao):
        if decisao == 'aprovado':
            obj.status = 'documentos_em_analise'
        elif decisao == 'rejeitado':
            obj.status = 'documentos_pendentes'
        obj.save(update_fields=['status'])
