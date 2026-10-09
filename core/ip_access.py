"""Lista global de redes aprovadas, independente do histórico de IPs."""
from core.client_ip import obter_ip_cliente, registrar_ip_acesso
from core.models import ControleAcessoIP, PermissaoIP


def controle_ip_ativo():
    return ControleAcessoIP.objects.filter(pk=1, ativo=True).exists()


def ip_aprovado(request):
    address = obter_ip_cliente(request)
    return bool(address and PermissaoIP.objects.filter(ip_address=address, status='aprovado').exists())


def solicitar_ip(request):
    """Só uma identidade autenticada pode gerar uma solicitação; não reabre recusas."""
    address = obter_ip_cliente(request)
    if not request.user.is_authenticated or not address:
        return None
    registrar_ip_acesso(request)
    registro, _ = PermissaoIP.objects.get_or_create(
        ip_address=address, defaults={'solicitado_por': request.user},
    )
    return registro
