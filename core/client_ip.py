"""IP da conexão autenticada, respeitando a origem dos cabeçalhos."""
import logging
from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)


def normalizar_ip(value):
    try:
        address = ip_address((value or '').strip())
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        return str(address)
    except ValueError:
        return None


def obter_ip_cliente(request):
    if settings.IP_CLIENTE_VERCEL:
        # Estes cabeçalhos são definidos pela borda da Vercel.
        value = request.META.get('HTTP_X_VERCEL_FORWARDED_FOR')
        if not value:
            value = request.META.get('HTTP_X_FORWARDED_FOR')
        # Não usar REMOTE_ADDR na Vercel: pode ser o proxy da plataforma.
        return normalizar_ip(value)
    return normalizar_ip(request.META.get('REMOTE_ADDR'))


def registrar_ip_acesso(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return
    address = obter_ip_cliente(request)
    if not address:
        return
    from core.models import IPUsuario

    agora = timezone.now()
    try:
        registro, created = IPUsuario.objects.get_or_create(
            usuario=request.user, ip_address=address,
            defaults={'primeiro_acesso': agora, 'ultimo_acesso': agora, 'confirmado': True},
        )
        if not created and (
            not registro.confirmado or agora - registro.ultimo_acesso >= timedelta(minutes=5)
        ):
            IPUsuario.objects.filter(pk=registro.pk).update(ultimo_acesso=agora, confirmado=True)
    except Exception:
        # Falha de telemetria não deve impedir o usuário de entrar no ERP.
        logger.exception('Falha ao registrar IP de acesso do usuário %s', request.user.pk)
