"""ERP Grupo PremiumBR — Views do Core (Login, Dashboard, Notificações)"""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.middleware.csrf import get_token
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.csrf import csrf_failure as default_csrf_failure

from core.access import user_has_access, user_is_executive
from core.models import (
    AprovacaoRegistro, ArquivoImportado, Fornecedor, LogAtividade,
    PerfilUsuario, Notificacao, Unidade,
)
from core.forms import (
    FornecedorForm, RevisaoPagamentoImportadoForm, UnidadeForm, UsuarioERPForm,
)
from recrutamento.models import Vaga, Candidato
from admissional.models import (
    Admissao, Colaborador, PagamentoColaborador, PresencaDiaria,
)
from core.services.importacao_arquivo_central import classificar_pagamento_regra
from core.direct_uploads import verify_direct_upload
from core.services.assistente_provisorio import (
    categorias_permitidas, registrar_documento, responder_pergunta,
)
from django.db import transaction
from administrativo.models import DemandaAdministrativa
from sesmet.models import IntegracaoSeguranca, OrdemServico, RegistroEPI
from compras.models import Material, PedidoCompra, SolicitacaoMaterial
from financeiro.models import DocumentoFinanceiro, LancamentoERP
from manutencao.models import RegistroManutencao


logger = logging.getLogger(__name__)


@login_required
def arquivo_central(request):
    if not user_has_access(
        request.user,
        permission='core.view_arquivoimportado',
        profiles=('admin', 'rh', 'financeiro', 'gestor'),
    ):
        raise PermissionDenied

    arquivos = ArquivoImportado.objects.select_related(
        'content_type'
    ).prefetch_related('origens')
    categoria = request.GET.get('categoria', '').strip()
    categorias_validas = {value for value, _ in ArquivoImportado.CATEGORIAS}
    if categoria in categorias_validas:
        arquivos = arquivos.filter(categoria=categoria)
    else:
        categoria = ''
    status = request.GET.get('status', '').strip()
    status_validos = {value for value, _ in ArquivoImportado.STATUS}
    if status in status_validos:
        arquivos = arquivos.filter(status=status)
    else:
        status = ''
    query = request.GET.get('q', '').strip()[:120]
    if query:
        arquivos = arquivos.filter(
            Q(nome_original__icontains=query)
            | Q(origens__caminho_relativo__icontains=query)
            | Q(subcategoria__icontains=query)
        ).distinct()

    paginator = Paginator(arquivos, 100)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/arquivo_central.html', {
        'page': page,
        'arquivos': page.object_list,
        'query': query,
        'categoria_filter': categoria,
        'status_filter': status,
        'categoria_choices': ArquivoImportado.CATEGORIAS,
        'status_choices': ArquivoImportado.STATUS,
        'total_arquivos': ArquivoImportado.objects.count(),
        'total_revisar': ArquivoImportado.objects.filter(status='revisar').count(),
        'total_vinculados': ArquivoImportado.objects.filter(status='vinculado').count(),
    })


@login_required
def baixar_arquivo_importado(request, pk):
    arquivo = get_object_or_404(ArquivoImportado, pk=pk)
    if arquivo.importado_por_id != request.user.pk and not user_has_access(
        request.user,
        permission='core.view_arquivoimportado',
        profiles=('admin', 'rh', 'financeiro', 'gestor'),
    ):
        raise PermissionDenied
    return redirect(arquivo.arquivo.url)


@login_required
@transaction.atomic
def revisar_arquivo_importado(request, pk):
    if not user_has_access(
        request.user,
        permission='core.change_arquivoimportado',
        profiles=('admin', 'rh', 'financeiro', 'gestor'),
    ):
        raise PermissionDenied
    arquivo = get_object_or_404(ArquivoImportado.objects.select_for_update(), pk=pk)
    metadados = arquivo.metadados or {}
    data_texto = metadados.get('data_pagamento', '')
    colaborador_sugerido = Colaborador.objects.filter(
        pk=metadados.get('colaborador_sugerido_id')
    ).first()
    try:
        valor_sugerido = Decimal(str(metadados.get('valor', '')).replace(',', '.'))
    except InvalidOperation:
        valor_sugerido = None
    tipo = classificar_pagamento_regra(
        arquivo.subcategoria,
        parse_date(data_texto) if data_texto else None,
        valor_sugerido,
        colaborador_sugerido,
    )
    if tipo not in dict(PagamentoColaborador.TIPOS):
        tipo = 'salario'
    competencia = data_texto
    if data_texto and tipo in {'salario', 'salario_beneficios', 'prestacao_servico', 'freelancer', 'distrato'}:
        competencia = f'{data_texto[:7]}-01'
    initial = {
        'colaborador': metadados.get('colaborador_sugerido_id'),
        'tipo': tipo,
        'competencia': competencia,
        'valor': str(metadados.get('valor', '')).replace(',', '.'),
        'data_pagamento': data_texto,
        'observacao': f'Importado do arquivo {arquivo.nome_original}',
    }
    if request.method == 'POST':
        form = RevisaoPagamentoImportadoForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            identificador = metadados.get('identificador_transacao') or f'arquivo:{arquivo.sha256}'
            pagamento = PagamentoColaborador.objects.filter(
                identificador_transacao=identificador
            ).first() or PagamentoColaborador(identificador_transacao=identificador)
            pagamento.colaborador = data['colaborador']
            pagamento.tipo = data['tipo']
            pagamento.competencia = data['competencia']
            pagamento.competencia_fim = data['competencia'] + (
                timedelta(days=6)
                if data['tipo'] in {'vale_transporte', 'ajuda_custo'}
                else timedelta(0)
            )
            pagamento.valor = data['valor']
            pagamento.data_vencimento = data['data_pagamento']
            pagamento.status = 'pago'
            pagamento.data_pagamento = data['data_pagamento']
            pagamento.recorrente = data['tipo'] in {'vale_transporte', 'ajuda_custo'}
            pagamento.observacao = data['observacao']
            if not pagamento.criado_por_id:
                pagamento.criado_por = request.user
            pagamento.full_clean()
            pagamento.save()
            arquivo.content_object = pagamento
            arquivo.status = 'vinculado'
            arquivo.motivo_revisao = ''
            arquivo.save(update_fields=[
                'content_type', 'object_id', 'status', 'motivo_revisao', 'atualizado_em'
            ])
            messages.success(request, 'Arquivo revisado e pagamento vinculado com sucesso.')
            return redirect('arquivo_central')
    else:
        form = RevisaoPagamentoImportadoForm(initial=initial)
    return render(request, 'core/revisar_arquivo_importado.html', {
        'arquivo': arquivo,
        'form': form,
    })


def _usuario_admin(user):
    return (
        user.is_authenticated
        and (
            user_is_executive(user)
            or getattr(getattr(user, 'perfil', None), 'perfil', None) == 'admin'
        )
    )


def _next_url_segura(request, default='/'):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default


def csrf_failure_view(request, reason=''):
    """Recupera login expirado no Safari sem desativar a protecao CSRF."""
    if request.path_info == '/login/':
        params = {'csrf': 'expired'}
        next_url = request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            params['next'] = next_url
        return redirect(f"{reverse('login')}?{urlencode(params)}")
    return default_csrf_failure(request, reason=reason)


@require_GET
@never_cache
def csrf_token_json(request):
    """Entrega um token novo imediatamente antes do envio do login."""
    return JsonResponse({'csrfToken': get_token(request)})


@never_cache
@ensure_csrf_cookie
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
    from core.assistant_navigation import (
        answer_with_process, processes_for_user, recommend_process,
    )

    pergunta_ia = ''
    resposta_ia = ''
    processo_recomendado = None
    if request.method == 'POST' and request.POST.get('acao') == 'perguntar_ia':
        pergunta_ia = request.POST.get('pergunta', '').strip()[:500]
        if pergunta_ia:
            resposta_ia = answer_with_process(
                request.user,
                pergunta_ia,
                responder_pergunta(request.user, pergunta_ia),
            )
            processo_recomendado = recommend_process(request.user, pergunta_ia)
        else:
            resposta_ia = 'Conte o que você precisa fazer para eu indicar o processo e a tela correta.'
    is_visao_executiva = user_is_executive(request.user)
    pode_ver_documentos_pendentes = user_has_access(
        request.user,
        permission='admissional.view_colaborador',
        profiles=('rh',),
        groups=('Admissional_RH',),
    )
    pode_ver_presenca = user_has_access(
        request.user,
        permission='admissional.change_presencadiaria',
        profiles=('rh', 'gestor'),
        groups=('Admissional_RH',),
    )

    # Perfil do usuário (pode não existir em modo demo)
    perfil = None
    try:
        perfil = request.user.perfil
    except Exception:
        logger.debug('Usuario sem perfil associado', exc_info=True)
        pass

    try:
        from sesmet.services import sincronizar_alertas_epi
        sincronizar_alertas_epi()
    except Exception:
        logger.exception('Falha ao sincronizar alertas de EPI no dashboard')

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
        documentos_incompletos = (
            Colaborador.objects.exclude(status__in=['inativo', 'desligado'])
            .com_documentacao_incompleta().count()
            if pode_ver_documentos_pendentes else 0
        )
        presencas_definidas_hoje = PresencaDiaria.objects.filter(
            data=hoje,
        ).exclude(status='indefinido').values('colaborador_id').distinct().count()
        presencas_nao_definidas = (
            max(0, colaboradores_ativos - presencas_definidas_hoje)
            if pode_ver_presenca else 0
        )

        # Módulo 3 - Administrativo
        demandas_abertas  = DemandaAdministrativa.objects.exclude(status__in=['arquivada']).count()
        demandas_urgentes = DemandaAdministrativa.objects.filter(
            prioridade='urgente').exclude(status='arquivada').count()

        # Módulo 4 - SESMET
        epis_vencidos    = RegistroEPI.objects.filter(
            data_validade__lt=hoje,
            tipo_movimentacao='retirada',
            ciclo_ativo=True,
        ).count()
        epis_vencendo_7d = RegistroEPI.objects.filter(
            data_validade__gte=hoje,
            data_validade__lte=hoje + timezone.timedelta(days=7),
            tipo_movimentacao='retirada', ciclo_ativo=True).count()

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

        atividades_recentes = []
        areas_movimentadas = []
        movimentacoes_hoje = decisoes_hoje = aprovacoes_pendentes_total = 0
        if is_visao_executiva:
            inicio_hoje = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
            inicio_periodo = inicio_hoje - timezone.timedelta(days=6)
            atividades_recentes = LogAtividade.objects.select_related('usuario').only(
                'usuario__first_name', 'usuario__last_name', 'usuario__username',
                'acao', 'modulo', 'url', 'criado_em',
            )[:12]
            movimentacoes_hoje = LogAtividade.objects.filter(criado_em__gte=inicio_hoje).count()
            areas_movimentadas = list(
                LogAtividade.objects.filter(criado_em__gte=inicio_periodo)
                .values('modulo').annotate(total=Count('id')).order_by('-total', 'modulo')[:8]
            )
            aprovacoes_pendentes_total = AprovacaoRegistro.objects.filter(status='pendente').count()
            decisoes_hoje = AprovacaoRegistro.objects.filter(
                status__in=['aprovado', 'rejeitado'], decidido_em__gte=inicio_hoje,
            ).count()

    except Exception:
        logger.exception('Falha ao carregar os indicadores do dashboard')
        # Banco indisponível — retorna zeros
        vagas_abertas = vagas_em_selecao = candidatos_pendentes = 0
        admissoes_em_andamento = colaboradores_ativos = 0
        documentos_incompletos = 0
        presencas_nao_definidas = 0
        demandas_abertas = demandas_urgentes = 0
        epis_vencidos = epis_vencendo_7d = 0
        solicitacoes_pendentes = materiais_criticos = 0
        docs_em_auditoria = lancamentos_pendentes = 0
        notificacoes_nao_lidas = 0
        ultimas_notificacoes = []
        vagas_recentes = admissoes_recentes = demandas_recentes = []
        atividades_recentes = areas_movimentadas = []
        movimentacoes_hoje = decisoes_hoje = aprovacoes_pendentes_total = 0

    context = {
        'perfil': perfil,
        'vagas_abertas': vagas_abertas,
        'vagas_em_selecao': vagas_em_selecao,
        'candidatos_pendentes': candidatos_pendentes,
        'admissoes_em_andamento': admissoes_em_andamento,
        'colaboradores_ativos': colaboradores_ativos,
        'documentos_incompletos': documentos_incompletos,
        'pode_ver_documentos_pendentes': pode_ver_documentos_pendentes,
        'pode_ver_presenca': pode_ver_presenca,
        'presencas_nao_definidas': presencas_nao_definidas,
        'demandas_abertas': demandas_abertas,
        'demandas_urgentes': demandas_urgentes,
        'epis_vencidos': epis_vencidos,
        'epis_vencendo_7d': epis_vencendo_7d,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'materiais_criticos': materiais_criticos,
        'docs_em_auditoria': docs_em_auditoria,
        'lancamentos_pendentes': lancamentos_pendentes,
        'notificacoes_nao_lidas': notificacoes_nao_lidas,
        'ultimas_notificacoes': ultimas_notificacoes,
        'vagas_recentes': vagas_recentes,
        'admissoes_recentes': admissoes_recentes,
        'demandas_recentes': demandas_recentes,
        'is_visao_executiva': is_visao_executiva,
        'atividades_recentes': atividades_recentes,
        'areas_movimentadas': areas_movimentadas,
        'movimentacoes_hoje': movimentacoes_hoje,
        'decisoes_hoje': decisoes_hoje,
        'aprovacoes_pendentes_total': aprovacoes_pendentes_total,
        'hoje': hoje,
        'modo_demo': False,
    }
    context.update({
        'processos_assistente': processes_for_user(request.user),
        'pergunta_ia': pergunta_ia,
        'resposta_ia': resposta_ia,
        'processo_recomendado': processo_recomendado,
    })
    return render(request, 'dashboard.html', context)


@login_required
def ajuda(request):
    """Guia leve e contextual, disponível a todos os perfis do ERP."""
    return render(request, 'core/ajuda.html')


@login_required
def assistente_erp(request):
    """Assistente provisoria: consulta local e ingestao automatica de documentos."""
    from core.assistant_navigation import (
        answer_with_process, processes_for_user, recommend_process,
    )

    resposta = ''
    processo_recomendado = None
    if request.method == 'POST':
        acao = request.POST.get('acao', '')
        if acao == 'perguntar':
            pergunta = request.POST.get('pergunta', '').strip()[:500]
            resposta = answer_with_process(
                request.user,
                pergunta,
                responder_pergunta(request.user, pergunta),
            )
            processo_recomendado = recommend_process(request.user, pergunta)
        elif acao == 'documento':
            try:
                key = verify_direct_upload(request, 'assistente_documento', required=True)
                nome = request.POST.get(
                    'direct_upload_assistente_documento_original_name', 'documento'
                ).strip()
                from pathlib import Path
                nome = Path(nome).name[:255] or 'documento'
                extensao_real = Path(key).suffix.lower()
                if Path(nome).suffix.lower() != extensao_real:
                    nome = f'{Path(nome).stem[:220]}{extensao_real}'
                tipos = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
                arquivo, criado = registrar_documento(
                    request.user, key, nome, tipos.get(extensao_real, ''),
                    request.POST.get('categoria', ''),
                )
                if criado:
                    if arquivo.status == 'erro':
                        messages.warning(request, arquivo.motivo_revisao)
                    elif arquivo.status == 'vinculado':
                        messages.success(request, 'Documento processado e vinculado automaticamente ao cadastro.')
                    else:
                        messages.success(request, 'Documento classificado e armazenado automaticamente.')
                else:
                    messages.info(request, 'Esse documento ja estava registrado; mantivemos apenas uma copia.')
                return redirect(f'{reverse("assistente_erp")}?arquivo={arquivo.pk}')
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            except Exception:
                logger.exception('Falha ao registrar documento pelo assistente provisorio')
                messages.error(request, 'Nao foi possivel analisar o documento. Tente novamente.')

    permitidas = categorias_permitidas(request.user)
    arquivo_id = request.GET.get('arquivo', '')
    arquivo_atual = None
    if arquivo_id.isdigit():
        arquivo_atual = ArquivoImportado.objects.filter(
            pk=int(arquivo_id), importado_por=request.user
        ).first()
    recentes = ArquivoImportado.objects.filter(importado_por=request.user)[:8]
    return render(request, 'core/assistente_erp.html', {
        'resposta': resposta,
        'pergunta': request.POST.get('pergunta', '')[:500],
        'categorias': [item for item in ArquivoImportado.CATEGORIAS if item[0] in permitidas],
        'arquivos_recentes': recentes,
        'arquivo_atual': arquivo_atual,
        'ia_configurada': False,
        'processos_assistente': processes_for_user(request.user),
        'processo_recomendado': processo_recomendado,
    })


@login_required
def cadastros_gerais(request):
    busca = request.GET.get('q', '').strip()[:100]
    fornecedores = Fornecedor.objects.all()
    unidades = Unidade.objects.all()
    if busca:
        fornecedores = fornecedores.filter(
            Q(codigo__icontains=busca) | Q(razao_social__icontains=busca)
            | Q(nome_fantasia__icontains=busca) | Q(cnpj__icontains=busca)
        )
        unidades = unidades.filter(
            Q(codigo__icontains=busca) | Q(nome__icontains=busca)
            | Q(cidade__icontains=busca) | Q(estado__icontains=busca)
        )
    return render(request, 'core/cadastros_gerais.html', {
        'fornecedores': fornecedores,
        'unidades': unidades,
        'busca': busca,
    })


def _salvar_cadastro(request, *, form_class, instance=None, titulo, retorno):
    form = form_class(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        registro = form.save(commit=False)
        if not registro.pk:
            registro.criado_por = request.user
        registro.save()
        from django.core.cache import cache
        cache.delete('cadastros_gerais_opcoes_v1')
        messages.success(request, f'{titulo} {registro.codigo} salvo com sucesso.')
        return redirect(retorno)
    return render(request, 'core/form_cadastro_geral.html', {'form': form, 'titulo': titulo})


@login_required
def novo_fornecedor(request):
    return _salvar_cadastro(
        request, form_class=FornecedorForm, titulo='Fornecedor', retorno='cadastros_gerais'
    )


@login_required
def editar_fornecedor(request, pk):
    return _salvar_cadastro(
        request, form_class=FornecedorForm, instance=get_object_or_404(Fornecedor, pk=pk),
        titulo='Fornecedor', retorno='cadastros_gerais',
    )


@login_required
def nova_unidade(request):
    return _salvar_cadastro(
        request, form_class=UnidadeForm, titulo='Unidade', retorno='cadastros_gerais'
    )


@login_required
def editar_unidade(request, pk):
    return _salvar_cadastro(
        request, form_class=UnidadeForm, instance=get_object_or_404(Unidade, pk=pk),
        titulo='Unidade', retorno='cadastros_gerais',
    )




@login_required
def notificacoes_json(request):
    """API JSON para notificações (AJAX)"""
    try:
        notifs = Notificacao.objects.filter(
            destinatario=request.user, lida=False
        )
        total = notifs.count()
        recentes = notifs.values(
            'id', 'tipo', 'modulo', 'titulo', 'mensagem', 'url_acao', 'criado_em'
        )[:20]
        return JsonResponse({'notificacoes': list(recentes), 'total': total})
    except Exception:
        return JsonResponse({'notificacoes': [], 'total': 0})


@login_required
@require_POST
def marcar_notificacao_lida(request, pk):
    Notificacao.objects.filter(pk=pk, destinatario=request.user).update(lida=True)
    return JsonResponse({'status': 'ok'})


@login_required
def lista_usuarios(request):
    if not _usuario_admin(request.user):
        raise PermissionDenied
    usuarios = User.objects.select_related('perfil').prefetch_related('groups').order_by(
        '-is_active', 'first_name', 'username'
    )
    return render(request, 'core/lista_usuarios.html', {'usuarios': usuarios})


@login_required
def novo_usuario(request):
    if not _usuario_admin(request.user):
        raise PermissionDenied
    form = UsuarioERPForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f'Usuario {user.get_full_name() or user.username} criado com sucesso.')
        return redirect('lista_usuarios')
    return render(request, 'core/form_usuario.html', {'form': form, 'acao': 'Novo'})


@login_required
def editar_usuario(request, pk):
    if not _usuario_admin(request.user):
        raise PermissionDenied
    user = get_object_or_404(User, pk=pk)
    form = UsuarioERPForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        if user.pk == request.user.pk and not form.cleaned_data['is_active']:
            form.add_error('is_active', 'Voce nao pode desativar a propria conta.')
        else:
            user = form.save()
            messages.success(request, f'Usuario {user.get_full_name() or user.username} atualizado.')
            return redirect('lista_usuarios')
    return render(request, 'core/form_usuario.html', {'form': form, 'acao': 'Editar', 'usuario_editado': user})



@login_required
def auditoria_sistema(request):
    """
    Dashboard de Auditoria Global. Exclusivo para CEO/Admin.
    """
    if not user_is_executive(request.user):
        messages.error(request, '⛔ Acesso restrito à Diretoria.')
        return redirect('dashboard')

    busca = request.GET.get('q', '').strip()[:100]
    modulo_filtro = request.GET.get('modulo', '').strip()[:100]
    acao_filtro = request.GET.get('acao', '').strip()
    filtros_acao = {
        'criar': 'Criou',
        'editar': 'Editou',
        'aprovar': 'Aprovou',
        'rejeitar': 'Rejeitou',
    }

    try:
        logs_query = LogAtividade.objects.select_related('usuario')
        total_logs = logs_query.count()
        if busca:
            logs_query = logs_query.filter(
                Q(usuario__username__icontains=busca)
                | Q(usuario__first_name__icontains=busca)
                | Q(usuario__last_name__icontains=busca)
                | Q(acao__icontains=busca)
                | Q(url__icontains=busca)
            )
        if modulo_filtro:
            logs_query = logs_query.filter(modulo=modulo_filtro)
        if acao_filtro in filtros_acao:
            logs_query = logs_query.filter(acao__startswith=filtros_acao[acao_filtro])
        filtros_ativos = bool(busca or modulo_filtro or acao_filtro in filtros_acao)
        total_filtrados = logs_query.count() if filtros_ativos else total_logs
        logs = Paginator(logs_query, 30).get_page(request.GET.get('page'))
        modulos_disponiveis = list(
            LogAtividade.objects.order_by('modulo')
            .values_list('modulo', flat=True).distinct()
        )
    except Exception:
        logger.exception('Falha ao carregar os registros de auditoria')
        messages.warning(request, 'Não foi possível carregar os registros de auditoria.')
        logs = Paginator([], 30).get_page(1)
        total_logs = total_filtrados = 0
        modulos_disponiveis = []
    
    try:
        destaque_id = int(request.GET.get('destaque', ''))
    except (TypeError, ValueError):
        destaque_id = None

    query_params = request.GET.copy()
    query_params.pop('page', None)
    return render(request, 'core/auditoria.html', {
        'logs': logs,
        'destaque_id': destaque_id,
        'busca': busca,
        'modulo_filtro': modulo_filtro,
        'acao_filtro': acao_filtro,
        'modulos_disponiveis': modulos_disponiveis,
        'total_logs': total_logs,
        'total_filtrados': total_filtrados,
        'filtros_query': query_params.urlencode(),
    })


@login_required
def painel_sla_processos(request):
    """
    Dashboard de Tempo de Processos (SLA). Exclusivo para CEO/Admin.
    """
    if not user_is_executive(request.user):
        messages.error(request, '⛔ Acesso restrito à Diretoria.')
        return redirect('dashboard')

    agora = timezone.now()
    hoje_sla = timezone.localdate()
    processos = []

    # 1. Aprovações Genéricas Pendentes
    aprovacoes = AprovacaoRegistro.objects.filter(status='pendente').only(
        'titulo', 'modulo', 'criado_em'
    )
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
            'url': reverse('detalhe_aprovacao', args=[ap.pk]),
        })

    # 2. Pedidos de Compra Pendentes
    pedidos = PedidoCompra.objects.exclude(
        status='concluido'
    ).select_related('solicitacao__material', 'aprovado_por').only(
        'status', 'fornecedor', 'criado_em', 'aprovado_por__first_name',
        'aprovado_por__last_name', 'solicitacao__material__nome',
    )
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
            'url': reverse('detalhe_solicitacao', args=[pc.solicitacao_id]),
        })

    # 3. Documentos Financeiros Pendentes
    docs = DocumentoFinanceiro.objects.exclude(
        status='arquivado'
    ).select_related('recebido_por').only(
        'numero_documento', 'valor', 'status', 'criado_em',
        'recebido_por__first_name', 'recebido_por__last_name',
    )
    for doc in docs:
        delta = agora - doc.criado_em
        processos.append({
            'tipo': 'Documento Financeiro',
            'modulo': 'Financeiro',
            'titulo': f"{doc.numero_documento} - R$ {doc.valor}",
            'status': doc.get_status_display(),
            'responsavel': doc.recebido_por.get_full_name() if doc.recebido_por else 'Financeiro / Auditoria',
            'criado_em': doc.criado_em,
            'dias': delta.days,
            'horas': delta.seconds // 3600,
            'alerta': delta.days >= 2,
            'url': reverse('detalhe_documento', args=[doc.pk]),
        })

    # 4. Vagas ainda abertas
    for vaga in Vaga.objects.exclude(status__in=['preenchida', 'cancelada']).only(
        'nome_vaga', 'unidade', 'status', 'gestor_responsavel', 'criado_em'
    ):
        processos.append({
            'tipo': 'Vaga', 'modulo': 'Recrutamento',
            'titulo': f'{vaga.nome_vaga} - {vaga.unidade}',
            'status': vaga.get_status_display(),
            'responsavel': vaga.gestor_responsavel or 'RH / Recrutamento',
            'criado_em': vaga.criado_em,
            'url': reverse('detalhe_vaga', args=[vaga.pk]),
        })

    # 5. Processos admissionais ainda em andamento
    for admissao in Admissao.objects.exclude(status='concluido').select_related(
        'responsavel_rh'
    ).only(
        'candidato_nome', 'vaga_nome', 'status', 'criado_em',
        'responsavel_rh__first_name', 'responsavel_rh__last_name',
    ):
        processos.append({
            'tipo': 'Admissão', 'modulo': 'Admissional',
            'titulo': f'{admissao.candidato_nome} - {admissao.vaga_nome}',
            'status': admissao.get_status_display(),
            'responsavel': admissao.responsavel_rh.get_full_name() if admissao.responsavel_rh else 'RH / Admissional',
            'criado_em': admissao.criado_em,
            'url': reverse('detalhe_admissao', args=[admissao.pk]),
        })

    # 6. Demandas administrativas não arquivadas
    for demanda in DemandaAdministrativa.objects.exclude(status='arquivada').select_related(
        'responsavel'
    ).only(
        'titulo', 'status', 'criado_em',
        'responsavel__first_name', 'responsavel__last_name',
    ):
        processos.append({
            'tipo': 'Demanda Administrativa', 'modulo': 'Administrativo',
            'titulo': demanda.titulo, 'status': demanda.get_status_display(),
            'responsavel': demanda.responsavel.get_full_name() if demanda.responsavel else 'Administrativo',
            'criado_em': demanda.criado_em,
            'url': reverse('detalhe_demanda', args=[demanda.pk]),
        })

    # 7. Solicitações de materiais ainda não encerradas
    solicitacoes_encerradas = ['atendido_interno', 'entregue', 'cancelado']
    for solicitacao in SolicitacaoMaterial.objects.exclude(
        status__in=solicitacoes_encerradas
    ).select_related('material', 'atendida_por').only(
        'status', 'unidade_destino', 'criado_em', 'material__nome',
        'atendida_por__first_name', 'atendida_por__last_name',
    ):
        processos.append({
            'tipo': 'Solicitação de Material', 'modulo': 'Compras',
            'titulo': f'{solicitacao.material.nome} - {solicitacao.unidade_destino}',
            'status': solicitacao.get_status_display(),
            'responsavel': solicitacao.atendida_por.get_full_name() if solicitacao.atendida_por else 'Compras / Almoxarifado',
            'criado_em': solicitacao.criado_em,
            'url': reverse('detalhe_solicitacao', args=[solicitacao.pk]),
        })

    # 8. Lançamentos financeiros não finalizados
    for lancamento in LancamentoERP.objects.exclude(status='finalizado').select_related(
        'documento', 'lancado_por'
    ).only(
        'status', 'criado_em', 'documento__numero_documento',
        'lancado_por__first_name', 'lancado_por__last_name',
    ):
        processos.append({
            'tipo': 'Lançamento ERP', 'modulo': 'Financeiro',
            'titulo': f'Documento {lancamento.documento.numero_documento}',
            'status': lancamento.get_status_display(),
            'responsavel': lancamento.lancado_por.get_full_name() if lancamento.lancado_por else 'Financeiro',
            'criado_em': lancamento.criado_em,
            'url': reverse('validar_lancamento', args=[lancamento.pk]),
        })

    # 9. Manutenções ainda abertas
    for manutencao in RegistroManutencao.objects.exclude(
        status__in=['concluida', 'cancelada']
    ).select_related('ativo', 'registrado_por').only(
        'status', 'criado_em', 'ativo__nome', 'ativo__numero_patrimonio',
        'registrado_por__first_name', 'registrado_por__last_name',
    ):
        processos.append({
            'tipo': 'Manutenção', 'modulo': 'Manutenção',
            'titulo': f'{manutencao.ativo.numero_patrimonio} - {manutencao.ativo.nome}',
            'status': manutencao.get_status_display(),
            'responsavel': manutencao.registrado_por.get_full_name() if manutencao.registrado_por else 'Manutenção / Patrimônio',
            'criado_em': manutencao.criado_em,
            'url': reverse('lista_manutencoes'),
        })

    # 10. Pendências de integração e ciclos de EPI do SESMET
    for integracao in IntegracaoSeguranca.objects.filter(
        concluida=False, colaborador__status='ativo'
    ).select_related('colaborador').only(
        'apresentador', 'criado_em', 'colaborador__nome'
    ):
        processos.append({
            'tipo': 'Integração de Segurança', 'modulo': 'SESMET',
            'titulo': integracao.colaborador.nome,
            'status': 'Integração pendente',
            'responsavel': integracao.apresentador or 'SESMET',
            'criado_em': integracao.criado_em,
            'url': reverse('dashboard_sesmet'),
        })

    for registro in RegistroEPI.objects.filter(
        tipo_movimentacao='retirada',
        ciclo_ativo=True,
        data_validade__lte=hoje_sla + timezone.timedelta(days=15),
        colaborador__status='ativo',
    ).select_related('colaborador', 'equipamento', 'registrado_por').only(
        'criado_em', 'data_validade', 'colaborador__nome', 'equipamento__nome',
        'registrado_por__first_name', 'registrado_por__last_name',
    ):
        dias = (registro.data_validade - hoje_sla).days
        processos.append({
            'tipo': 'Ciclo de EPI', 'modulo': 'SESMET',
            'titulo': f'{registro.colaborador.nome} - {registro.equipamento.nome}',
            'status': 'Prazo vencido' if dias < 0 else f'Vence em {dias} dia(s)',
            'responsavel': registro.registrado_por.get_full_name() if registro.registrado_por else 'SESMET',
            'criado_em': registro.criado_em,
            'url': reverse('dashboard_sesmet'),
        })

    for ordem in OrdemServico.objects.filter(
        assinado=False, colaborador__status='ativo'
    ).select_related('colaborador', 'emitido_por').only(
        'numero', 'criado_em', 'colaborador__nome',
        'emitido_por__first_name', 'emitido_por__last_name',
    ):
        processos.append({
            'tipo': 'Ordem de Serviço', 'modulo': 'SESMET',
            'titulo': f'{ordem.numero} - {ordem.colaborador.nome}',
            'status': 'Aguardando assinatura',
            'responsavel': ordem.emitido_por.get_full_name() if ordem.emitido_por else 'SESMET',
            'criado_em': ordem.criado_em,
            'url': reverse('dashboard_sesmet'),
        })

    # Normaliza tempos e níveis de atenção para todas as fontes.
    for processo in processos:
        total_horas = max(0, int((agora - processo['criado_em']).total_seconds() // 3600))
        processo['total_horas'] = total_horas
        processo['dias'] = total_horas // 24
        processo['horas'] = total_horas % 24
        processo['alerta'] = total_horas >= 48
        processo['critico'] = total_horas >= 168
        processo.setdefault('url', '')

    processos = sorted(processos, key=lambda item: item['total_horas'], reverse=True)
    todos_processos = processos

    modulos = sorted({processo['modulo'] for processo in todos_processos})
    modulo_filter = request.GET.get('modulo', '').strip()
    faixa_filter = request.GET.get('faixa', '').strip()
    if modulo_filter and modulo_filter not in modulos:
        modulo_filter = ''
    if faixa_filter not in {'', 'alerta', 'critico'}:
        faixa_filter = ''

    if modulo_filter:
        processos = [p for p in processos if p['modulo'] == modulo_filter]
    if faixa_filter == 'alerta':
        processos = [p for p in processos if p['alerta']]
    elif faixa_filter == 'critico':
        processos = [p for p in processos if p['critico']]

    resumo_modulos = []
    for modulo in modulos:
        itens = [p for p in todos_processos if p['modulo'] == modulo]
        resumo_modulos.append({
            'nome': modulo,
            'total': len(itens),
            'alertas': sum(1 for p in itens if p['alerta']),
            'criticos': sum(1 for p in itens if p['critico']),
            'mais_antigo': max((p['dias'] for p in itens), default=0),
            'percentual': round(len(itens) * 100 / len(todos_processos)) if todos_processos else 0,
        })

    total = len(todos_processos)
    total_horas = sum(p['total_horas'] for p in todos_processos)
    faixas = [
        {'nome': 'Até 24 horas', 'total': sum(1 for p in todos_processos if p['total_horas'] < 24)},
        {'nome': 'De 1 a 2 dias', 'total': sum(1 for p in todos_processos if 24 <= p['total_horas'] < 48)},
        {'nome': 'De 2 a 7 dias', 'total': sum(1 for p in todos_processos if 48 <= p['total_horas'] < 168)},
        {'nome': 'Acima de 7 dias', 'total': sum(1 for p in todos_processos if p['total_horas'] >= 168)},
    ]
    for faixa in faixas:
        faixa['percentual'] = round(faixa['total'] * 100 / total) if total else 0

    return render(request, 'core/painel_sla.html', {
        'processos': processos,
        'total_processos': total,
        'total_alertas': sum(1 for p in todos_processos if p['alerta']),
        'total_criticos': sum(1 for p in todos_processos if p['critico']),
        'media_horas': round(total_horas / total) if total else 0,
        'resumo_modulos': resumo_modulos,
        'faixas': faixas,
        'modulos': modulos,
        'modulo_filter': modulo_filter,
        'faixa_filter': faixa_filter,
        'atualizado_em': agora,
    })


def permission_denied_view(request, exception=None):
    return render(request, 'errors/error.html', {
        'status_code': 403,
        'titulo': 'Acesso não autorizado',
        'mensagem': 'Seu usuário não possui permissão para acessar esta área.',
        'orientacao': 'Volte ao painel ou solicite a liberação da área ao administrador.',
    }, status=403)


def page_not_found_view(request, exception=None):
    return render(request, 'errors/error.html', {
        'status_code': 404,
        'titulo': 'Página não encontrada',
        'mensagem': 'O endereço acessado não existe ou não está mais disponível.',
        'orientacao': 'Confira o endereço ou volte ao painel para continuar.',
    }, status=404)


def server_error_view(request):
    # O handler 500 nao usa os context processors, pois a falha original pode
    # ser justamente uma indisponibilidade do banco usada por algum processor.
    conteudo = loader.get_template('errors/error.html').render({
        'status_code': 500,
        'titulo': 'Não foi possível concluir',
        'mensagem': 'O sistema encontrou uma falha inesperada.',
        'orientacao': 'Tente novamente em alguns instantes. Se persistir, informe o suporte.',
    })
    return HttpResponse(conteudo, status=500)
