from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.client_ip import normalizar_ip, obter_ip_cliente
from core.ip_access import controle_ip_ativo, ip_aprovado, solicitar_ip
from core.models import ControleAcessoIP, IPUsuario, LogAtividade, PermissaoIP
from core.views import _usuario_admin


@login_required
@require_GET
@never_cache
def aguardando_ip(request):
    if not controle_ip_ativo() or ip_aprovado(request):
        return redirect('dashboard')
    registro = solicitar_ip(request)
    return render(request, 'core/aguardando_ip.html', {
        'endereco_ip': obter_ip_cliente(request),
        'bloqueado': bool(registro and registro.status == 'bloqueado'),
    })


@login_required
@require_GET
@never_cache
def controle_ips(request):
    if not _usuario_admin(request.user):
        raise PermissionDenied
    registros = list(PermissaoIP.objects.select_related('solicitado_por', 'decidido_por'))
    usuarios_por_ip = {}
    for historico in IPUsuario.objects.filter(ip_address__in=[item.ip_address for item in registros]).select_related('usuario'):
        usuarios_por_ip.setdefault(historico.ip_address, []).append(historico.usuario)
    for registro in registros:
        registro.usuarios_observados = usuarios_por_ip.get(registro.ip_address, [])
    ordem = {'pendente': 0, 'aprovado': 1, 'bloqueado': 2}
    registros.sort(key=lambda item: ordem.get(item.status, 3))
    return render(request, 'core/controle_ips.html', {
        'ativo': controle_ip_ativo(), 'endereco_ip': obter_ip_cliente(request),
        'registros': registros,
        'pendentes': sum(item.status == 'pendente' for item in registros),
        'aprovados': sum(item.status == 'aprovado' for item in registros),
        'bloqueados': sum(item.status == 'bloqueado' for item in registros),
    })


@login_required
@require_POST
@never_cache
@transaction.atomic
def alterar_controle_ip(request):
    if not _usuario_admin(request.user):
        raise PermissionDenied
    acao = request.POST.get('acao')
    address = obter_ip_cliente(request)
    config, _ = ControleAcessoIP.objects.get_or_create(pk=1)
    config = ControleAcessoIP.objects.select_for_update().get(pk=config.pk)
    alvo = None
    if acao == 'ativar':
        if not address:
            messages.error(request, 'Não foi possível identificar seu IP. O bloqueio não foi ativado.')
            return redirect('controle_ips')
        PermissaoIP.objects.update_or_create(ip_address=address, defaults={
            'status': 'aprovado', 'decidido_por': request.user, 'decidido_em': timezone.now(),
        })
        config.ativo = True
        config.save(update_fields=['ativo'])
        alvo = address
        messages.success(request, 'Bloqueio ativado. Seu IP atual foi aprovado.')
    elif acao == 'desativar':
        config.ativo = False
        config.save(update_fields=['ativo'])
        messages.success(request, 'Bloqueio por IP desativado. O login continua obrigatório.')
    elif acao in {'aprovar', 'bloquear', 'cadastrar'}:
        if acao == 'cadastrar':
            alvo = normalizar_ip(request.POST.get('ip_address'))
            if not alvo:
                messages.error(request, 'Informe um endereço IPv4 ou IPv6 válido, sem porta ou faixa de rede.')
                return redirect('controle_ips')
            registro, _ = PermissaoIP.objects.get_or_create(ip_address=alvo)
        else:
            registro_id = request.POST.get('registro_id', '')
            if not registro_id.isdecimal():
                raise PermissionDenied
            registro = get_object_or_404(PermissaoIP, pk=registro_id)
        alvo = registro.ip_address
        if acao == 'bloquear' and config.ativo and alvo == address:
            messages.error(request, 'Você não pode revogar sua rede atual com o bloqueio ativo. Use outra rede aprovada ou desative o controle primeiro.')
            return redirect('controle_ips')
        registro.status = 'bloqueado' if acao == 'bloquear' else 'aprovado'
        registro.decidido_por = request.user
        registro.decidido_em = timezone.now()
        registro.save(update_fields=['status', 'decidido_por', 'decidido_em'])
        messages.success(request, f'IP {alvo}: {registro.get_status_display().lower()}.')
    else:
        raise PermissionDenied
    LogAtividade.objects.create(
        usuario=request.user, acao=f'Controle de IP: {acao}', modulo='sistema',
        url=request.path, ip_address=address, detalhes=f'IP: {alvo or "—"}',
    )
    request._audit_no_change = True
    return redirect('controle_ips')
