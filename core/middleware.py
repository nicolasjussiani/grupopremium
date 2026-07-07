import os
from django.contrib.auth.models import User, AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.contrib import messages


class StatelessDemoMiddleware(MiddlewareMixin):
    """
    Middleware inteligente para o ERP Grupo PremiumBR:

    - Se DATABASE_URL estiver configurada (Supabase/produção):
        Deixa o Django Auth normal funcionar (login real).

    - Se DATABASE_URL NÃO estiver configurada (demo local / Vercel sem DB):
        Injeta um superusuário fake em memória, sem tocar no banco.
        Isso evita o erro "attempt to write a readonly database" no Vercel.
    """

    _demo_user = None  # Cache do usuário demo (evita query repetida)

    def process_request(self, request):
        # Se tiver Supabase configurado, deixa o Django Auth normal agir
        if os.environ.get('DATABASE_URL'):
            return  # Auth real — não interfere

        # Modo Demo: injeta usuário fake sem nenhuma query ao banco
        if StatelessDemoMiddleware._demo_user is None:
            # Tenta pegar um usuário real uma única vez (pode falhar no Vercel)
            try:
                StatelessDemoMiddleware._demo_user = User.objects.first()
            except Exception:
                StatelessDemoMiddleware._demo_user = None

        if StatelessDemoMiddleware._demo_user:
            request.user = StatelessDemoMiddleware._demo_user
        else:
            # Fallback total: usuário fake em memória, zero queries
            fake = User()
            fake.id = 1
            fake.pk = 1
            fake.username = 'admin_demo'
            fake.first_name = 'Admin'
            fake.last_name = 'Demo'
            fake.email = 'admin@ecopremium.com.br'
            fake.is_active = True
            fake.is_staff = True
            fake.is_superuser = True
            fake._state.adding = False  # Evita que Django tente salvar
            request.user = fake


class AcessoModuloMiddleware(MiddlewareMixin):
    """
    Middleware que restringe o acesso aos módulos com base no perfil do usuário.
    O Admin (superuser) e o usuário Luiz têm acesso irrestrito.
    """
    def process_request(self, request):
        if not request.user.is_authenticated:
            return None
            
        path = request.path_info
        
        # Ignorar URLs liberadas ou de sistema
        if path.startswith('/admin/') or path.startswith('/static/') or path.startswith('/media/') or path == '/' or path.startswith('/login') or path.startswith('/logout') or path.startswith('/api/'):
            return None
            
        # Acesso irrestrito
        if request.user.is_superuser or request.user.username.lower() == 'luiz':
            return None
            
        perfil = request.user.perfil.perfil if hasattr(request.user, 'perfil') else 'operacional'
        
        regras = {
            '/recrutamento/': ['rh', 'gestor'],
            '/admissional/': ['rh', 'gestor'],
            '/administrativo/': ['gestor'],
            '/sesmet/': ['sesmet', 'gestor'],
            '/compras/': ['compras', 'gestor'],
            '/financeiro/': ['financeiro', 'gestor'],
        }
        
        for prefix, perfis_permitidos in regras.items():
            if path.startswith(prefix):
                if perfil not in perfis_permitidos:
                    messages.error(request, '⛔ Acesso negado! Você não tem permissão para acessar este módulo.')
                    return redirect('dashboard')
                break
                
        return None

class AuditLogMiddleware(MiddlewareMixin):
    """
    Middleware para interceptar ações de escrita (POST) e gravar log de auditoria automaticamente.
    """
    def process_request(self, request):
        if request.method == 'POST' and request.user.is_authenticated:
            path = request.path_info
            
            # Ignora ações repetitivas ou irrelevantes para auditoria de negócio
            if path.startswith('/login') or path.startswith('/logout') or path.startswith('/api/notificacoes'):
                return None
            
            partes = path.strip('/').split('/')
            modulo = partes[0] if partes else 'sistema'
            
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')

            # Sanitização dos dados (remove tokens e senhas)
            dados = request.POST.copy()
            if 'password' in dados:
                dados['password'] = '***'
            if 'csrfmiddlewaretoken' in dados:
                del dados['csrfmiddlewaretoken']

            # Inferência da ação baseada na URL
            acao = f"Ação submetida em: {path}"
            if 'aprovar' in path:
                acao = "Aprovou um registro/documento"
            elif 'rejeitar' in path:
                acao = "Rejeitou um registro/documento"
            elif 'novo' in path or 'criar' in path:
                acao = "Criou um novo registro"
            elif 'editar' in path or 'atualizar' in path:
                acao = "Editou um registro existente"

            from core.models import LogAtividade
            try:
                LogAtividade.objects.create(
                    usuario=request.user,
                    acao=acao,
                    modulo=modulo,
                    url=path,
                    ip_address=ip,
                    detalhes=str(dados.dict())[:1000]
                )
            except Exception:
                pass # Evita quebrar o sistema se o log falhar

        return None

