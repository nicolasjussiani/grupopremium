"""ERP Grupo Premium — Views do Core (Login, Dashboard, Notificações)"""
import os
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q
from django.utils import timezone

from core.models import PerfilUsuario, Notificacao
from recrutamento.models import Vaga, Candidato
from admissional.models import Admissao, Colaborador
from administrativo.models import DemandaAdministrativa
from sesmet.models import RegistroEPI
from compras.models import SolicitacaoMaterial, Material
from financeiro.models import DocumentoFinanceiro, LancamentoERP


from django.views.decorators.csrf import csrf_exempt

_MODO_DEMO = not bool(os.environ.get('DATABASE_URL'))

@csrf_exempt
def login_view(request):
    # ── Modo Demo (sem Supabase configurado) ──────────────────────────────────
    # Não toca no banco de dados. Qualquer acesso é permitido.
    if _MODO_DEMO:
        if request.method == 'POST':
            next_url = request.GET.get('next', '/')
            response = redirect(next_url)
            response.set_cookie('demo_logged_in', 'true', max_age=86400)
            return response
        # Se já tem cookie, vai direto pro dashboard
        if request.COOKIES.get('demo_logged_in'):
            return redirect('dashboard')
        return render(request, 'login.html', {'modo_demo': True})

    # ── Modo Real (Supabase configurado) ─────────────────────────────────────
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            messages.error(request, 'Usuário ou senha incorretos.')

    return render(request, 'login.html', {'modo_demo': False})


def logout_view(request):
    if _MODO_DEMO:
        response = redirect('login')
        response.delete_cookie('demo_logged_in')
        return response
    # Modo real
    logout(request)
    return redirect('login')



@login_required
def dashboard(request):
    hoje = timezone.now().date()

    # Perfil do usuário (pode não existir em modo demo)
    perfil = None
    try:
        perfil = request.user.perfil
    except Exception:
        pass

    # Todos os KPIs são protegidos — se o banco não estiver disponível,
    # retorna zeros e listas vazias (modo demo sem Supabase)
    try:
        from django.db.models import F as Fcompras

        # Módulo 1 - Recrutamento
        vagas_abertas       = Vaga.objects.exclude(status__in=['preenchida', 'cancelada']).count()
        vagas_em_selecao    = Vaga.objects.filter(status='em_selecao').count()
        candidatos_pendentes= Candidato.objects.exclude(etapa_atual__in=['aprovado', 'reprovado', 'desistente']).count()

        # Módulo 2 - Admissional
        admissoes_em_andamento = Admissao.objects.exclude(status__in=['concluido']).count()
        colaboradores_ativos   = Colaborador.objects.filter(status='ativo').count()

        # Módulo 3 - Administrativo
        demandas_abertas  = DemandaAdministrativa.objects.exclude(status__in=['arquivada']).count()
        demandas_urgentes = DemandaAdministrativa.objects.filter(
            prioridade='urgente').exclude(status='arquivada').count()

        # Módulo 4 - SESMET
        epis_vencidos    = RegistroEPI.objects.filter(data_validade__lt=hoje, status='ativo').count()
        epis_vencendo_7d = RegistroEPI.objects.filter(
            data_validade__gte=hoje,
            data_validade__lte=hoje + timezone.timedelta(days=7),
            status='ativo').count()

        # Módulo 5 - Compras
        solicitacoes_pendentes = SolicitacaoMaterial.objects.filter(
            status__in=['pendente', 'em_analise']).count()
        materiais_criticos = Material.objects.filter(
            quantidade_estoque__lte=Fcompras('estoque_minimo')).count()

        # Módulo 6 - Financeiro
        docs_em_auditoria    = DocumentoFinanceiro.objects.filter(
            status__in=['recebido', 'em_auditoria']).count()
        lancamentos_pendentes = LancamentoERP.objects.filter(
            status__in=['rascunho', 'em_validacao']).count()

        # Notificações
        notificacoes_nao_lidas  = Notificacao.objects.filter(destinatario=request.user, lida=False).count()
        ultimas_notificacoes    = Notificacao.objects.filter(destinatario=request.user).order_by('-criado_em')[:5]

        # Atividade recente
        vagas_recentes    = Vaga.objects.order_by('-criado_em')[:3]
        admissoes_recentes= Admissao.objects.order_by('-criado_em')[:3]
        demandas_recentes = DemandaAdministrativa.objects.order_by('-criado_em')[:3]

    except Exception:
        # Banco indisponível (modo demo sem Supabase) — retorna zeros
        vagas_abertas = vagas_em_selecao = candidatos_pendentes = 0
        admissoes_em_andamento = colaboradores_ativos = 0
        demandas_abertas = demandas_urgentes = 0
        epis_vencidos = epis_vencendo_7d = 0
        solicitacoes_pendentes = materiais_criticos = 0
        docs_em_auditoria = lancamentos_pendentes = 0
        notificacoes_nao_lidas = 0
        ultimas_notificacoes = []
        vagas_recentes = admissoes_recentes = demandas_recentes = []

    context = {
        'perfil': perfil,
        'vagas_abertas': vagas_abertas,
        'vagas_em_selecao': vagas_em_selecao,
        'candidatos_pendentes': candidatos_pendentes,
        'admissoes_em_andamento': admissoes_em_andamento,
        'colaboradores_ativos': colaboradores_ativos,
        'demandas_abertas': demandas_abertas,
        'demandas_urgentes': demandas_urgentes,
        'epis_vencidos': epis_vencidos,
        'epis_vencendo_7d': epis_vencendo_7d,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'docs_em_auditoria': docs_em_auditoria,
        'lancamentos_pendentes': lancamentos_pendentes,
        'notificacoes_nao_lidas': notificacoes_nao_lidas,
        'ultimas_notificacoes': ultimas_notificacoes,
        'vagas_recentes': vagas_recentes,
        'admissoes_recentes': admissoes_recentes,
        'demandas_recentes': demandas_recentes,
        'hoje': hoje,
        'modo_demo': _MODO_DEMO,
    }
    return render(request, 'dashboard.html', context)




@login_required
def notificacoes_json(request):
    """API JSON para notificações (AJAX)"""
    try:
        notifs = Notificacao.objects.filter(
            destinatario=request.user, lida=False
        ).values('id', 'tipo', 'modulo', 'titulo', 'mensagem', 'url_acao', 'criado_em')
        return JsonResponse({'notificacoes': list(notifs), 'total': notifs.count()})
    except Exception:
        return JsonResponse({'notificacoes': [], 'total': 0})


@login_required
def marcar_notificacao_lida(request, pk):
    if request.method == 'POST':
        try:
            Notificacao.objects.filter(pk=pk, destinatario=request.user).update(lida=True)
        except Exception:
            pass
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)



@login_required
def marcar_notificacao_lida(request, pk):
    if request.method == 'POST':
        Notificacao.objects.filter(pk=pk, destinatario=request.user).update(lida=True)
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)


# ── TEMPORÁRIO: View de diagnóstico para debug da Vercel ──────────────────────
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings as django_settings

@csrf_exempt
def debug_env(request):
    """View temporária para diagnosticar variáveis de ambiente na Vercel.
    REMOVER DEPOIS DE RESOLVER O PROBLEMA!"""
    import sys
    info = {
        'DATABASE_URL_exists': bool(os.environ.get('DATABASE_URL')),
        'DATABASE_URL_starts_with': (os.environ.get('DATABASE_URL', '')[:30] + '...') if os.environ.get('DATABASE_URL') else 'NOT SET',
        'DB_ENGINE': django_settings.DATABASES['default']['ENGINE'],
        'DB_HOST': django_settings.DATABASES['default'].get('HOST', 'N/A'),
        'DB_NAME': str(django_settings.DATABASES['default'].get('NAME', 'N/A')),
        'SESSION_ENGINE': django_settings.SESSION_ENGINE,
        'VERCEL_env': os.environ.get('VERCEL', 'NOT SET'),
        'env_file_exists': (django_settings.BASE_DIR / '.env').exists(),
        'MIDDLEWARE_count': len(django_settings.MIDDLEWARE),
        'MIDDLEWARE': django_settings.MIDDLEWARE,
        'CSRF_TRUSTED_ORIGINS': django_settings.CSRF_TRUSTED_ORIGINS,
        'python_path': sys.path[:5],
        'cwd': os.getcwd(),
        'BASE_DIR': str(django_settings.BASE_DIR),
        'all_env_keys_with_DB_or_SUPA': [k for k in os.environ.keys() if 'DB' in k.upper() or 'SUPA' in k.upper() or 'DATABASE' in k.upper()],
    }
    return JsonResponse(info, json_dumps_params={'indent': 2})


from django.core.management import call_command
from django.http import HttpResponse

@login_required
def run_migrations_view(request):
    if not request.user.is_superuser:
        return HttpResponse("Acesso negado", status=403)
    try:
        call_command("migrate", interactive=False)
        return HttpResponse("Migrações aplicadas no banco de dados!")
    except Exception as e:
        return HttpResponse(f"Erro: {e}", status=500)
