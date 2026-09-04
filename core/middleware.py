import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger(__name__)


class AcessoModuloMiddleware(MiddlewareMixin):
    """Restringe a navegacao de cada modulo conforme o perfil do usuario."""

    REGRAS = {
        '/recrutamento/': {'rh', 'gestor', 'sesmet'},
        '/admissional/': {'rh', 'gestor', 'sesmet'},
        '/administrativo/': {'gestor'},
        '/sesmet/': {'sesmet', 'gestor', 'rh'},
        '/compras/': {'compras', 'gestor'},
        '/financeiro/': {'financeiro', 'gestor'},
        '/manutencao/': {'sesmet', 'gestor', 'compras', 'rh'},
    }

    ROTAS_LIVRES = ('/admin/', '/static/', '/media/', '/login', '/logout')

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        path = request.path_info
        if path == '/' or path.startswith(self.ROTAS_LIVRES):
            return None

        if request.user.is_superuser or request.user.groups.filter(name='Admin_Global').exists():
            return None

        perfil_obj = getattr(request.user, 'perfil', None)
        perfil = getattr(perfil_obj, 'perfil', 'operacional')

        for prefix, perfis_permitidos in self.REGRAS.items():
            if path.startswith(prefix) and perfil not in perfis_permitidos:
                messages.error(request, 'Acesso negado: seu perfil nao permite acessar este modulo.')
                return redirect('dashboard')
        return None


class AuditLogMiddleware(MiddlewareMixin):
    """Registra POSTs concluidos sem copiar dados pessoais ou credenciais."""

    ROTAS_IGNORADAS = ('/login', '/logout', '/api/notificacoes')

    def process_response(self, request, response):
        if not (
            request.method == 'POST'
            and getattr(request, 'user', None)
            and request.user.is_authenticated
            and response.status_code < 400
        ):
            return response

        path = request.path_info
        if path.startswith(self.ROTAS_IGNORADAS):
            return response

        partes = path.strip('/').split('/')
        modulo = partes[0] if partes and partes[0] else 'sistema'
        campos = sorted(k for k in request.POST.keys() if k != 'csrfmiddlewaretoken')

        acao = f'Acao submetida em: {path}'
        if 'aprovar' in path:
            acao = 'Aprovou um registro/documento'
        elif 'rejeitar' in path:
            acao = 'Rejeitou um registro/documento'
        elif 'novo' in path or 'criar' in path:
            acao = 'Criou um novo registro'
        elif 'editar' in path or 'atualizar' in path:
            acao = 'Editou um registro existente'

        from core.models import LogAtividade

        try:
            LogAtividade.objects.create(
                usuario=request.user,
                acao=acao,
                modulo=modulo,
                url=path,
                ip_address=request.META.get('REMOTE_ADDR'),
                detalhes=f"Campos enviados: {', '.join(campos)}"[:1000],
            )
        except Exception:
            logger.exception('Falha ao registrar auditoria para %s', path)

        return response
