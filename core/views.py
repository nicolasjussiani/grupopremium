"""ERP Grupo PremiumBR — Views do Core (Login, Dashboard, Notificações)"""
import logging
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import PerfilUsuario, Notificacao
from recrutamento.models import Vaga, Candidato
from admissional.models import Admissao, Colaborador
from administrativo.models import DemandaAdministrativa
from sesmet.models import RegistroEPI
from compras.models import SolicitacaoMaterial, Material
from financeiro.models import DocumentoFinanceiro, LancamentoERP


logger = logging.getLogger(__name__)


def _next_url_segura(request, default='/'):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default


def login_view(request):
    # ── Modo Demo (sem Supabase configurado) ──────────────────────────────────
    # Não toca no banco de dados. Qualquer acesso é permitido.
    # ── Modo Real (Supabase configurado) ─────────────────────────────────────
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(_next_url_segura(request))
        else:
            messages.error(request, 'Usuário ou senha incorretos.')

    return render(request, 'login.html')


@require_POST
def logout_view(request):
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
        logger.debug('Usuario sem perfil associado', exc_info=True)
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
        epis_vencidos    = RegistroEPI.objects.filter(data_validade__lt=hoje, tipo_movimentacao='retirada').count()
        epis_vencendo_7d = RegistroEPI.objects.filter(
            data_validade__gte=hoje,
            data_validade__lte=hoje + timezone.timedelta(days=7),
            tipo_movimentacao='retirada').count()

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
        logger.exception('Falha ao carregar os indicadores do dashboard')
        # Banco indisponível — retorna zeros
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
        'modo_demo': False,
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
@require_POST
def marcar_notificacao_lida(request, pk):
    Notificacao.objects.filter(pk=pk, destinatario=request.user).update(lida=True)
    return JsonResponse({'status': 'ok'})



from core.models import LogAtividade

@login_required
def auditoria_sistema(request):
    """
    Dashboard de Auditoria Global. Exclusivo para CEO/Admin.
    """
    if not (request.user.is_superuser or request.user.groups.filter(name='Admin_Global').exists()):
        messages.error(request, '⛔ Acesso restrito à Diretoria.')
        return redirect('dashboard')

    try:
        logs = list(LogAtividade.objects.all().select_related('usuario')[:500])
    except Exception:
        logger.exception('Falha ao carregar os registros de auditoria')
        messages.warning(request, 'Não foi possível carregar os registros de auditoria.')
        logs = []
    
    return render(request, 'core/auditoria.html', {
        'logs': logs
    })


from django.utils import timezone
from core.models import AprovacaoRegistro
from compras.models import PedidoCompra
from financeiro.models import DocumentoFinanceiro

@login_required
def painel_sla_processos(request):
    """
    Dashboard de Tempo de Processos (SLA). Exclusivo para CEO/Admin.
    """
    if not (request.user.is_superuser or request.user.groups.filter(name='Admin_Global').exists()):
        messages.error(request, '⛔ Acesso restrito à Diretoria.')
        return redirect('dashboard')

    agora = timezone.now()
    processos = []

    # 1. Aprovações Genéricas Pendentes
    aprovacoes = AprovacaoRegistro.objects.filter(status='pendente')
    for ap in aprovacoes:
        delta = agora - ap.criado_em
        processos.append({
            'tipo': 'Aprovação Genérica',
            'modulo': ap.get_modulo_display(),
            'titulo': ap.titulo,
            'status': 'Pendente',
            'responsavel': 'Gestor / Diretoria',
            'criado_em': ap.criado_em,
            'dias': delta.days,
            'horas': delta.seconds // 3600,
            'alerta': delta.days >= 2,
        })

    # 2. Pedidos de Compra Pendentes
    pedidos = PedidoCompra.objects.filter(status__in=['em_cotacao', 'aguardando_aprovacao'])
    for pc in pedidos:
        delta = agora - pc.criado_em
        resp = pc.aprovado_por.get_full_name() if pc.aprovado_por else 'Setor de Compras'
        processos.append({
            'tipo': 'Pedido de Compra',
            'modulo': 'Compras',
            'titulo': f"{pc.solicitacao.material.nome} - {pc.fornecedor}",
            'status': pc.get_status_display(),
            'responsavel': resp,
            'criado_em': pc.criado_em,
            'dias': delta.days,
            'horas': delta.seconds // 3600,
            'alerta': delta.days >= 2,
        })

    # 3. Documentos Financeiros Pendentes
    docs = DocumentoFinanceiro.objects.filter(status__in=['recebido', 'em_auditoria', 'aguardando_correcao'])
    for doc in docs:
        delta = agora - doc.criado_em
        processos.append({
            'tipo': 'Documento Financeiro',
            'modulo': 'Financeiro',
            'titulo': f"{doc.numero_documento} - R$ {doc.valor}",
            'status': doc.get_status_display(),
            'responsavel': 'Financeiro / Auditoria',
            'criado_em': doc.criado_em,
            'dias': delta.days,
            'horas': delta.seconds // 3600,
            'alerta': delta.days >= 2,
        })

    # Ordenar pelos mais demorados
    processos = sorted(processos, key=lambda x: x['criado_em'])

    return render(request, 'core/painel_sla.html', {
        'processos': processos
    })
