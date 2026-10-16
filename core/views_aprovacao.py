"""ERP Grupo PremiumBR ÔÇö Views da Linha de Aprova├º├úo"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Count, Q
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError

from core.access import user_has_access, user_is_executive
from core.approval_workflow import (
    FINALIDADE_OPERACIONAL, FINALIDADE_PAGAMENTO, MODELOS_PAGAMENTO,
    usuario_e_aprovador, usuario_tem_papel_aprovador,
)
from core.models import AprovacaoRegistro, LogAtividade, Notificacao
from admissional.models import Colaborador


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
    if user_is_executive(user):
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


def _aprovacoes_do_usuario(user):
    """Cada responsável acessa sua finalidade; decisões mantêm o acesso histórico."""
    historico = ~Q(status='pendente') & (
        Q(destinatario=user)
        | Q(destinatario__isnull=True, modulo__in=_modulos_do_usuario(user))
    )
    modelos_pagamento = Q(pk__in=[])
    for app_label, model in MODELOS_PAGAMENTO:
        modelos_pagamento |= Q(content_type__app_label=app_label, content_type__model=model)
    finalidades_autorizadas = Q(pk__in=[])
    if usuario_e_aprovador(user, FINALIDADE_PAGAMENTO):
        finalidades_autorizadas |= Q(finalidade=FINALIDADE_PAGAMENTO) & modelos_pagamento
    if usuario_e_aprovador(user, FINALIDADE_OPERACIONAL):
        finalidades_autorizadas |= Q(finalidade=FINALIDADE_OPERACIONAL) & ~modelos_pagamento
    pendentes = Q(status='pendente', destinatario=user) & finalidades_autorizadas
    return AprovacaoRegistro.objects.filter(pendentes | historico)


@login_required
def painel_mobile(request):
    """PWA para todos; decisoes aparecem apenas a quem pode aprovar."""
    modulos = _modulos_do_usuario(request.user)
    aprovacoes = _aprovacoes_do_usuario(request.user).filter(
        status='pendente'
    ).select_related('solicitado_por').order_by('-criado_em')
    notificacoes = Notificacao.objects.filter(
        destinatario=request.user
    ).order_by('-criado_em')[:20]
    historico = _aprovacoes_do_usuario(request.user).filter(
        status__in=('aprovado', 'rejeitado')
    ).select_related('aprovado_por').order_by('-decidido_em')[:10]
    is_visao_executiva = user_is_executive(request.user)
    pode_ver_documentos_pendentes = user_has_access(
        request.user,
        permission='admissional.view_colaborador',
        profiles=('rh',),
        groups=('Admissional_RH',),
    )
    documentos_incompletos = (
        Colaborador.objects.exclude(status__in=['inativo', 'desligado'])
        .com_documentacao_incompleta().count()
        if pode_ver_documentos_pendentes else 0
    )
    atividades_recentes = []
    areas_movimentadas = []
    movimentacoes_hoje = decisoes_hoje = 0
    if is_visao_executiva:
        inicio_hoje = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        inicio_periodo = inicio_hoje - timezone.timedelta(days=6)
        atividades_recentes = LogAtividade.objects.select_related('usuario').only(
            'usuario__first_name', 'usuario__last_name', 'usuario__username',
            'acao', 'modulo', 'url', 'criado_em',
        )[:12]
        movimentacoes_hoje = LogAtividade.objects.filter(criado_em__gte=inicio_hoje).count()
        decisoes_hoje = AprovacaoRegistro.objects.filter(
            status__in=['aprovado', 'rejeitado'], decidido_em__gte=inicio_hoje,
        ).count()
        areas_movimentadas = list(
            LogAtividade.objects.filter(criado_em__gte=inicio_periodo)
            .values('modulo').annotate(total=Count('id')).order_by('-total', 'modulo')[:8]
        )
    return render(request, 'mobile/painel.html', {
        'aprovacoes': aprovacoes,
        'notificacoes': notificacoes,
        'historico': historico,
        'total_pendentes': aprovacoes.count(),
        'total_nao_lidas': Notificacao.objects.filter(
            destinatario=request.user, lida=False
        ).count(),
        'pode_aprovar': usuario_tem_papel_aprovador(request.user),
        'is_visao_executiva': is_visao_executiva,
        'atividades_recentes': atividades_recentes,
        'areas_movimentadas': areas_movimentadas,
        'movimentacoes_hoje': movimentacoes_hoje,
        'decisoes_hoje': decisoes_hoje,
        'pode_ver_documentos_pendentes': pode_ver_documentos_pendentes,
        'documentos_incompletos': documentos_incompletos,
    })


@login_required
def detalhe_aprovacao_mobile(request, pk):
    aprovacao = get_object_or_404(_aprovacoes_do_usuario(request.user), pk=pk)
    return render(request, 'mobile/detalhe_aprovacao.html', {'aprovacao': aprovacao})


@login_required
def status_mobile(request):
    pendentes = _aprovacoes_do_usuario(request.user).filter(status='pendente').count()
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
const CACHE = 'premiumbr-mobile-v7';
const ASSETS = ['/static/pwa-icon-192.png', '/static/pwa-icon-512.png', '/static/favicon.jpeg'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || event.request.mode === 'navigate') return;
  const url = new URL(event.request.url);
  if (url.origin === self.location.origin && ASSETS.includes(url.pathname)) {
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

    aprovacoes = _aprovacoes_do_usuario(request.user).filter(
        status='pendente',
    ).select_related('content_type', 'solicitado_por').order_by('-criado_em')

    # Filtros opcionais via GET
    modulo_filtro = request.GET.get('modulo', '')
    nivel_filtro = request.GET.get('nivel', '')

    if modulo_filtro:
        aprovacoes = aprovacoes.filter(modulo=modulo_filtro)
    if nivel_filtro:
        aprovacoes = aprovacoes.filter(nivel=nivel_filtro)

    # Hist├│rico recente (├║ltimas 20 decididas)
    historico = _aprovacoes_do_usuario(request.user).filter(
        status__in=['aprovado', 'rejeitado'],
    ).select_related('aprovado_por').order_by('-decidido_em')[:20]

    total_pendentes = _aprovacoes_do_usuario(request.user).filter(
        status='pendente'
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


def _pendencia_para_decisao(user, pk):
    """Bloqueia a origem antes da fila na mesma ordem das ações operacionais."""
    autorizadas = _aprovacoes_do_usuario(user)
    candidata = get_object_or_404(
        autorizadas.select_related('content_type'), pk=pk, status='pendente',
    )
    if candidata.finalidade == FINALIDADE_PAGAMENTO:
        modelo = candidata.content_type.model_class()
        get_object_or_404(modelo.objects.select_for_update(), pk=candidata.object_id)
    elif (
        candidata.content_type.app_label == 'financeiro'
        and candidata.content_type.model == 'lancamentoerp'
    ):
        from financeiro.models import DocumentoFinanceiro, LancamentoERP
        lancamento = get_object_or_404(LancamentoERP, pk=candidata.object_id)
        get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=lancamento.documento_id)
        get_object_or_404(LancamentoERP.objects.select_for_update(), pk=lancamento.pk)
    elif candidata.modulo == 'compras' and candidata.content_type.app_label == 'compras':
        from compras.models import PedidoCompra, RequisicaoCompra
        modelo = {
            'pedidocompra': PedidoCompra,
            'requisicaocompra': RequisicaoCompra,
        }.get(candidata.content_type.model)
        if modelo is not None:
            get_object_or_404(modelo.objects.select_for_update(), pk=candidata.object_id)
    elif (
        candidata.modulo == 'manutencao'
        and candidata.content_type.app_label == 'manutencao'
        and candidata.content_type.model == 'registromanutencao'
    ):
        from manutencao.models import Ativo, RegistroManutencao
        registro = get_object_or_404(RegistroManutencao, pk=candidata.object_id)
        get_object_or_404(Ativo.objects.select_for_update(), pk=registro.ativo_id)
        get_object_or_404(RegistroManutencao.objects.select_for_update(), pk=registro.pk)
    # O bloqueio da origem pode ter aguardado uma edição, exclusão ou decisão.
    # Revalida a fila e seu vínculo depois da espera, sem reutilizar o estado lido.
    return get_object_or_404(
        _aprovacoes_do_usuario(user).select_for_update(), pk=pk, status='pendente',
        content_type_id=candidata.content_type_id, object_id=candidata.object_id,
        modulo=candidata.modulo, finalidade=candidata.finalidade, destinatario=user,
    )


@login_required
@require_POST
@transaction.atomic
def aprovar_registro(request, pk):
    """Aprova um registro pendente."""
    aprovacao = _pendencia_para_decisao(request.user, pk)

    comentario = request.POST.get('comentario', '').strip()
    try:
        with transaction.atomic():
            aprovacao.status = 'aprovado'
            aprovacao.destinatario = request.user
            aprovacao.nivel = 2
            aprovacao.aprovado_por = request.user
            aprovacao.decidido_em = timezone.now()
            aprovacao.comentario = comentario
            aprovacao.save()
            _executar_callback_aprovacao(aprovacao, 'aprovado', request.user)
    except ValidationError as exc:
        return JsonResponse({'status': 'erro', 'mensagem': '; '.join(exc.messages)}, status=400)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'mensagem': 'Registro aprovado com sucesso!'})

    messages.success(request, f'Ô£à "{aprovacao.titulo}" aprovado com sucesso!')
    return _redirect_seguro(request)


@login_required
@require_POST
@transaction.atomic
def rejeitar_registro(request, pk):
    """Rejeita um registro pendente."""
    aprovacao = _pendencia_para_decisao(request.user, pk)

    motivo = request.POST.get('motivo_rejeicao', '').strip()
    if not motivo:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'erro', 'mensagem': 'Informe o motivo da rejei├º├úo.'}, status=400)
        messages.error(request, 'ÔØî Informe o motivo da rejei├º├úo.')
        return _redirect_seguro(request)

    try:
        with transaction.atomic():
            aprovacao.status = 'rejeitado'
            aprovacao.destinatario = request.user
            aprovacao.nivel = 2
            aprovacao.aprovado_por = request.user
            aprovacao.decidido_em = timezone.now()
            aprovacao.motivo_rejeicao = motivo
            aprovacao.save()
            _executar_callback_aprovacao(aprovacao, 'rejeitado', request.user)
    except ValidationError as exc:
        return JsonResponse({'status': 'erro', 'mensagem': '; '.join(exc.messages)}, status=400)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'mensagem': 'Registro rejeitado.'})

    messages.warning(request, f'­ƒÜ½ "{aprovacao.titulo}" rejeitado.')
    return _redirect_seguro(request)


@login_required
def detalhe_aprovacao(request, pk):
    """Exibe detalhes de uma aprova├º├úo (para modal ou p├ígina)."""
    aprovacao = get_object_or_404(_aprovacoes_do_usuario(request.user), pk=pk)
    return render(request, 'core/detalhe_aprovacao.html', {'aprovacao': aprovacao})


@login_required
def api_aprovacoes_pendentes_count(request):
    """API JSON: conta aprova├º├Áes pendentes do usu├írio (para badge no menu)."""
    total = _aprovacoes_do_usuario(request.user).filter(status='pendente').count()
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
    if aprovacao.finalidade == FINALIDADE_PAGAMENTO:
        from core.payment_approvals import validar_snapshot_pagamento
        validar_snapshot_pagamento(obj, aprovacao)
        return
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
    from compras.models import PedidoCompra, RequisicaoCompra
    if isinstance(obj, PedidoCompra):
        obj = PedidoCompra.objects.select_for_update().get(pk=obj.pk)
        if decisao == 'aprovado':
            obj.aprovar(usuario)
        elif decisao == 'rejeitado':
            obj.reprovar(aprovacao.motivo_rejeicao)
    elif isinstance(obj, RequisicaoCompra):
        obj = RequisicaoCompra.objects.select_for_update().get(pk=obj.pk)
        if decisao == 'aprovado':
            if obj.status == 'aguardando_adriana':
                obj.status = 'aguardando_ceo'
            obj.aprovar(usuario)
        elif decisao == 'rejeitado':
            obj.rejeitar()


def _callback_financeiro(obj, decisao, usuario, aprovacao):
    from financeiro.models import DocumentoFinanceiro, LancamentoERP
    if isinstance(obj, LancamentoERP):
        documento = DocumentoFinanceiro.objects.select_for_update().get(pk=obj.documento_id)
        obj = LancamentoERP.objects.select_for_update().get(pk=obj.pk)
        if documento.status == 'cancelado' or obj.status != 'em_validacao':
            raise ValidationError('Este lançamento não está disponível para validação.')
        if decisao == 'aprovado':
            obj.status = 'finalizado'
            obj.validado_por = usuario
            obj.finalizado_em = timezone.now()
            documento.status = 'arquivado'
        elif decisao == 'rejeitado':
            obj.status = 'rejeitado'
            obj.motivo_rejeicao = aprovacao.motivo_rejeicao
            documento.status = 'aprovado_lancamento'
        obj.save(update_fields=['status', 'validado_por', 'finalizado_em', 'motivo_rejeicao'])
        documento.save(update_fields=['status'])


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
    from manutencao.models import Ativo, RegistroManutencao
    if isinstance(obj, RegistroManutencao):
        ativo = Ativo.objects.select_for_update().get(pk=obj.ativo_id)
        obj = RegistroManutencao.objects.select_for_update().get(pk=obj.pk)
        if obj.status != 'aguardando_aprovacao':
            raise ValidationError('Esta manutenção não está aguardando aprovação.')
        if decisao == 'aprovado':
            if ativo.status == 'inativo':
                raise ValidationError('Não é possível aprovar a manutenção de um ativo inativo.')
            obj.status = 'aberta'
            ativo.status = 'manutencao'
            ativo.save(update_fields=['status', 'atualizado_em'])
        elif decisao == 'rejeitado':
            obj.status = 'cancelada'
            outras_abertas = RegistroManutencao.objects.filter(
                ativo=ativo,
                status__in=('aguardando_aprovacao', 'aberta', 'andamento'),
            ).exclude(pk=obj.pk).exists()
            if ativo.status == 'manutencao' and not outras_abertas:
                ativo.status = 'ativo'
                ativo.save(update_fields=['status', 'atualizado_em'])
        obj.save(update_fields=['status'])
