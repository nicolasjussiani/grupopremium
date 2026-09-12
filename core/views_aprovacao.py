"""ERP Grupo PremiumBR ÔÇö Views da Linha de Aprova├º├úo"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import AprovacaoRegistro
from core.models import Notificacao


def _redirect_seguro(request):
    destino = request.POST.get('next')
    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destino)
    return redirect('aprovacoes_pendentes')

# Mapa: grupo ÔåÆ m├│dulos que ele pode aprovar
GRUPOS_APROVADORES = {
    'Recrutamento_Gestor':   ['recrutamento'],
    'Admissional_RH':        ['admissional'],
    'Administrativo_Gestor': ['administrativo'],
    'SESMET_Gestor':         ['sesmet'],
    'Compras_Aprovador':     ['compras'],
    'Financeiro_Aprovador':  ['financeiro'],
    'Diretoria_Final':       ['recrutamento', 'admissional', 'administrativo', 'sesmet', 'compras', 'financeiro', 'manutencao'],
    'Admin_Global':          ['recrutamento', 'admissional', 'administrativo', 'sesmet', 'compras', 'financeiro', 'manutencao'],
    'Intermediario_Gestor':  ['administrativo', 'sesmet', 'compras', 'financeiro', 'manutencao'],
}


# Mapa: perfil legado → módulos que ele pode aprovar
PERFIS_APROVADORES = {
    'compras':         ['compras'],
    'estoque_compras': ['compras'],
    'gestor':          ['recrutamento', 'admissional', 'administrativo', 'sesmet', 'compras', 'financeiro', 'manutencao'],
    'admin':           ['recrutamento', 'admissional', 'administrativo', 'sesmet', 'compras', 'financeiro', 'manutencao'],
    'financeiro':      ['financeiro'],
    'rh':              ['admissional', 'recrutamento'],
    'sesmet':          ['sesmet'],
}


def _modulos_do_usuario(user):
    """Retorna a lista de módulos que o usuário pode aprovar."""
    if user.is_superuser:
        return ['recrutamento', 'admissional', 'administrativo', 'sesmet', 'compras', 'financeiro', 'manutencao']
    modulos = set()
    grupos_usuario = user.groups.values_list('name', flat=True)
    for grupo in grupos_usuario:
        modulos.update(GRUPOS_APROVADORES.get(grupo, []))

    # Fallback: verifica perfil legado se o usuário não está em nenhum grupo aprovador
    if not modulos:
        perfil_obj = getattr(user, 'perfil', None)
        perfil = getattr(perfil_obj, 'perfil', None)
        modulos.update(PERFIS_APROVADORES.get(perfil, []))

    return list(modulos)


@login_required
def painel_mobile(request):
    """PWA para todos; decisoes aparecem apenas a quem pode aprovar."""
    modulos = _modulos_do_usuario(request.user)
    aprovacoes = AprovacaoRegistro.objects.filter(
        status='pendente', modulo__in=modulos
    ).select_related('solicitado_por').order_by('-criado_em')
    notificacoes = Notificacao.objects.filter(
        destinatario=request.user
    ).order_by('-criado_em')[:20]
    historico = AprovacaoRegistro.objects.filter(
        modulo__in=modulos, status__in=('aprovado', 'rejeitado')
    ).select_related('aprovado_por').order_by('-decidido_em')[:10]
    return render(request, 'mobile/painel.html', {
        'aprovacoes': aprovacoes,
        'notificacoes': notificacoes,
        'historico': historico,
        'total_pendentes': aprovacoes.count(),
        'total_nao_lidas': Notificacao.objects.filter(
            destinatario=request.user, lida=False
        ).count(),
        'pode_aprovar': bool(modulos),
    })


@login_required
def detalhe_aprovacao_mobile(request, pk):
    aprovacao = get_object_or_404(
        AprovacaoRegistro,
        pk=pk,
        modulo__in=_modulos_do_usuario(request.user),
    )
    return render(request, 'mobile/detalhe_aprovacao.html', {'aprovacao': aprovacao})


@login_required
def status_mobile(request):
    pendentes = AprovacaoRegistro.objects.filter(
        status='pendente', modulo__in=_modulos_do_usuario(request.user)
    ).count()
    notificacoes_nao_lidas = Notificacao.objects.filter(
        destinatario=request.user, lida=False
    ).order_by('-criado_em')
    ultima = notificacoes_nao_lidas.first()
    return JsonResponse({
        'pendentes': pendentes,
        'nao_lidas': notificacoes_nao_lidas.count(),
        'ultima_notificacao': {
            'titulo': ultima.titulo,
            'mensagem': ultima.mensagem,
            'url': ultima.url_acao,
        } if ultima else None,
    })


@login_required
@require_POST
def marcar_notificacoes_mobile(request):
    Notificacao.objects.filter(destinatario=request.user, lida=False).update(lida=True)
    return redirect(f"{reverse('painel_mobile')}#notificacoes")


@login_required
@require_POST
def criar_notificacao_teste_mobile(request):
    """Cria um aviso inofensivo para validar a central e o PWA."""
    notificacao = Notificacao.objects.create(
        destinatario=request.user,
        tipo='info',
        modulo='sistema',
        titulo='Notificação de teste',
        mensagem='O sistema de notificações do PremiumBR está funcionando corretamente.',
        url_acao=f"{reverse('painel_mobile')}#notificacoes",
    )
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'ok',
            'titulo': notificacao.titulo,
            'mensagem': notificacao.mensagem,
            'url': notificacao.url_acao,
        })
    messages.success(request, 'Notifica├º├úo de teste criada com sucesso.')
    return redirect(f"{reverse('painel_mobile')}#notificacoes")


def pwa_manifest(request):
    return JsonResponse({
        'id': '/mobile/',
        'name': 'PremiumBR ERP',
        'short_name': 'PremiumBR',
        'description': 'Notifica├º├Áes, processos e aprova├º├Áes do Grupo PremiumBR.',
        'start_url': '/mobile/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait-primary',
        'prefer_related_applications': False,
        'background_color': '#f5f7fb',
        'theme_color': '#0d2149',
        'icons': [
            {
                'src': '/static/pwa-icon-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': '/static/pwa-icon-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any maskable',
            },
        ],
    }, content_type='application/manifest+json')


def service_worker(request):
    script = """
const CACHE = 'premiumbr-mobile-v4';
const ASSETS = ['/static/css/mobile.css?v=3', '/static/pwa-icon-192.png', '/static/pwa-icon-512.png', '/static/favicon.jpeg'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || event.request.mode === 'navigate') return;
  const url = new URL(event.request.url);
  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
  self.addEventListener('notificationclick', event => {
    event.notification.close();
    const destination = event.notification.data && event.notification.data.url;
    event.waitUntil(clients.openWindow(destination && destination.startsWith('/') ? destination : '/mobile/'));
  });
""".strip()
    response = HttpResponse(script, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


@login_required
def aprovacoes_pendentes(request):
    """Lista todas as aprova├º├Áes pendentes para o usu├írio logado."""
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

    # Hist├│rico recente (├║ltimas 20 decididas)
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
@transaction.atomic
def aprovar_registro(request, pk):
    """Aprova um registro pendente."""
    modulos = _modulos_do_usuario(request.user)
    aprovacao = get_object_or_404(
        AprovacaoRegistro.objects.select_for_update(),
        pk=pk,
        status='pendente',
        modulo__in=modulos,
    )

    comentario = request.POST.get('comentario', '').strip()
    aprovacao.status = 'aprovado'
    aprovacao.aprovado_por = request.user
    aprovacao.decidido_em = timezone.now()
    aprovacao.comentario = comentario
    aprovacao.save()

    # Callback: atualiza status do objeto vinculado se ele tiver m├®todo
    _executar_callback_aprovacao(aprovacao, 'aprovado', request.user)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'mensagem': 'Registro aprovado com sucesso!'})

    messages.success(request, f'Ô£à "{aprovacao.titulo}" aprovado com sucesso!')
    return _redirect_seguro(request)


@login_required
@require_POST
@transaction.atomic
def rejeitar_registro(request, pk):
    """Rejeita um registro pendente."""
    modulos = _modulos_do_usuario(request.user)
    aprovacao = get_object_or_404(
        AprovacaoRegistro.objects.select_for_update(),
        pk=pk,
        status='pendente',
        modulo__in=modulos,
    )

    motivo = request.POST.get('motivo_rejeicao', '').strip()
    if not motivo:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'erro', 'mensagem': 'Informe o motivo da rejei├º├úo.'}, status=400)
        messages.error(request, 'ÔØî Informe o motivo da rejei├º├úo.')
        return _redirect_seguro(request)

    aprovacao.status = 'rejeitado'
    aprovacao.aprovado_por = request.user
    aprovacao.decidido_em = timezone.now()
    aprovacao.motivo_rejeicao = motivo
    aprovacao.save()

    _executar_callback_aprovacao(aprovacao, 'rejeitado', request.user)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'mensagem': 'Registro rejeitado.'})

    messages.warning(request, f'­ƒÜ½ "{aprovacao.titulo}" rejeitado.')
    return _redirect_seguro(request)


@login_required
def detalhe_aprovacao(request, pk):
    """Exibe detalhes de uma aprova├º├úo (para modal ou p├ígina)."""
    modulos = _modulos_do_usuario(request.user)
    aprovacao = get_object_or_404(AprovacaoRegistro, pk=pk, modulo__in=modulos)
    return render(request, 'core/detalhe_aprovacao.html', {'aprovacao': aprovacao})


@login_required
def api_aprovacoes_pendentes_count(request):
    """API JSON: conta aprova├º├Áes pendentes do usu├írio (para badge no menu)."""
    modulos = _modulos_do_usuario(request.user)
    total = AprovacaoRegistro.objects.filter(status='pendente', modulo__in=modulos).count()
    return JsonResponse({'total': total})


# ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
# CALLBACKS POR M├ôDULO
# Quando aprova├º├úo/rejei├º├úo acontece, atualiza o status do objeto vinculado.
# ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ

def _executar_callback_aprovacao(aprovacao, decisao, usuario):
    """
    Chama o callback correto conforme o m├│dulo e decis├úo.
    Cada m├│dulo define o que acontece quando um item ├® aprovado/rejeitado.
    """
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
    elif modulo == 'manutencao':
        _callback_manutencao(obj, decisao, usuario)


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


def _callback_manutencao(obj, decisao, usuario):
    from manutencao.models import RegistroManutencao
    if isinstance(obj, RegistroManutencao):
        if decisao == 'aprovado':
            obj.status = 'aberta'
        elif decisao == 'rejeitado':
            obj.status = 'cancelada'
            obj.ativo.status = 'ativo'
            obj.ativo.save(update_fields=['status', 'atualizado_em'])
        obj.save(update_fields=['status'])
