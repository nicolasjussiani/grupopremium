import os
from django.contrib.auth.models import User, AnonymousUser
from django.utils.deprecation import MiddlewareMixin


class StatelessDemoMiddleware(MiddlewareMixin):
    """
    Middleware inteligente para o ERP Grupo Premium:

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

