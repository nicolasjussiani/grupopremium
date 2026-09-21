"""ERP Grupo PremiumBR — Views do Módulo 2: Admissional"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_date
from .models import (
    Admissao, Colaborador, DocumentoAdmissional, DocumentoColaborador,
    PagamentoColaborador, PresencaDiaria,
)
from .forms import ColaboradorForm, PagamentoColaboradorForm
from core.models import ArquivoImportado, Notificacao
from django.contrib.contenttypes.models import ContentType
from sesmet.models import IntegracaoSeguranca, RegistroEPI, OrdemServico
from django.contrib.auth.models import User
from core.access import access_required, user_has_access
from core.validators import validate_document_upload
from core.direct_uploads import assign_direct_upload, verify_direct_upload
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, JsonResponse
from django.utils.text import get_valid_filename
from django.urls import reverse
from django.views.decorators.http import require_POST
from urllib.parse import urlencode


@login_required
def lista_admissoes(request):
    admissoes = Admissao.objects.all().prefetch_related('documentos')
    status_filter = request.GET.get('status', '')
    if status_filter:
        admissoes = admissoes.filter(status=status_filter)
    return render(request, 'admissional/lista_admissoes.html', {
        'admissoes': admissoes,
        'status_filter': status_filter,
        'status_choices': Admissao.STATUS,
        'total_em_andamento': Admissao.objects.exclude(status='concluido').count(),
        'total_concluidos': Admissao.objects.filter(status='concluido').count(),
    })


@login_required
def detalhe_admissao(request, pk):
    admissao = get_object_or_404(Admissao, pk=pk)
    documentos = admissao.documentos.all()
    docs_aprovados = documentos.filter(status='aprovado').count()
    docs_total = documentos.count()
    percentual = int((docs_aprovados / docs_total * 100) if docs_total else 0)

    return render(request, 'admissional/detalhe_admissao.html', {
        'admissao': admissao,
        'documentos': documentos,
        'percentual': percentual,
        'docs_aprovados': docs_aprovados,
        'docs_total': docs_total,
        'todos_aprovados': docs_aprovados == docs_total and docs_total > 0,
    })


@login_required
@access_required(permission='admissional.change_documentoadmissional', profiles=('rh', 'gestor'))
@transaction.atomic
def atualizar_documento(request, admissao_pk, doc_pk):
    """Gateway de documentação: SIM (aprovado) ou NÃO (pendente/rejeitado)"""
    admissao = get_object_or_404(Admissao.objects.select_for_update(), pk=admissao_pk)
    doc = get_object_or_404(DocumentoAdmissional.objects.select_for_update(), pk=doc_pk, admissao=admissao)
    if request.method == 'POST':
        novo_status = request.POST.get('status')
        obs = request.POST.get('observacao', '')
        status_validos = {choice[0] for choice in DocumentoAdmissional.STATUS}
        if novo_status not in status_validos:
            messages.error(request, 'Status de documento invalido.')
            return redirect('detalhe_admissao', pk=admissao_pk)
        
        arquivo_upload = request.FILES.get('arquivo')
        direct_key = None
        try:
            direct_key = verify_direct_upload(request, 'arquivo')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return render(request, 'admissional/atualizar_documento.html', {'doc': doc, 'admissao': admissao})
        if arquivo_upload:
            try:
                validate_document_upload(arquivo_upload)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'admissional/atualizar_documento.html', {'doc': doc, 'admissao': admissao})
            doc.arquivo_nuvem = arquivo_upload
            doc.arquivo_nome = arquivo_upload.name
            doc.arquivo_mimetype = arquivo_upload.content_type
        elif direct_key:
            doc.arquivo_nuvem.name = direct_key
            doc.arquivo_nome = direct_key.rsplit('/', 1)[-1]
            extension = direct_key.rsplit('.', 1)[-1].lower()
            doc.arquivo_mimetype = {
                'pdf': 'application/pdf',
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
            }.get(extension, 'application/octet-stream')
            
        doc.status = novo_status
        doc.observacao = obs
        doc.save()

        if novo_status == 'rejeitado':
            admissao.status = 'documentos_pendentes'
            admissao.save()
            messages.warning(request,
                f'⚠️ GATEWAY: Documento "{doc.get_tipo_display()}" rejeitado. '
                f'Solicitação de correção registrada.')
        else:
            # Verificar se todos aprovados
            todos = admissao.documentos.all()
            if all(d.status == 'aprovado' for d in todos):
                admissao.status = 'cadastro_sistema'
                admissao.save()
                messages.success(request,
                    '✅ GATEWAY: Todos os documentos aprovados! Processo avança para cadastro no sistema.')
            else:
                messages.success(request, f'✅ Documento "{doc.get_tipo_display()}" aprovado.')

        return redirect('detalhe_admissao', pk=admissao_pk)

    return render(request, 'admissional/atualizar_documento.html', {'doc': doc, 'admissao': admissao})


@login_required
@access_required(permission='admissional.change_admissao', profiles=('rh', 'gestor'))
@require_POST
@transaction.atomic
def avancar_admissao(request, pk):
    """Avança o status do processo admissional"""
    admissao = get_object_or_404(Admissao.objects.select_for_update(), pk=pk)
    if request.method == 'POST':
        novo_status = request.POST.get('novo_status')
        obs = request.POST.get('observacoes', '')
        if obs:
            admissao.observacoes = obs

        fluxo_status = [
            'aguardando_documentos', 'documentos_em_analise', 'cadastro_sistema',
            'contrato_gerado', 'integracao', 'epis_entregues', 'liberado', 'concluido'
        ]

        transicoes = {
            'aguardando_documentos': {'documentos_em_analise'},
            'documentos_em_analise': {'documentos_pendentes', 'cadastro_sistema'},
            'documentos_pendentes': {'documentos_em_analise'},
            'cadastro_sistema': {'contrato_gerado'},
            'contrato_gerado': {'integracao'},
            'integracao': {'epis_entregues'},
            'epis_entregues': {'liberado'},
            'liberado': {'concluido'},
            'concluido': set(),
        }

        if novo_status in transicoes.get(admissao.status, set()):
            admissao.status = novo_status
            if novo_status == 'concluido':
                admissao.concluido_em = timezone.now()
                # Criar colaborador se ainda não existe E checkbox marcado
                gerar_colab = request.POST.get('gerar_colaborador') == 'sim'
                if not admissao.colaborador and gerar_colab:
                    cpf = request.POST.get('cpf', '').strip()
                    if not cpf:
                        messages.error(request, 'Informe o CPF/CNPJ para gerar o colaborador.')
                        transaction.set_rollback(True)
                        return redirect('detalhe_admissao', pk=pk)
                    data_inicio_str = request.POST.get('data_inicio')
                    data_inicio_obj = timezone.now().date()
                    if data_inicio_str:
                        from datetime import datetime
                        try:
                            data_inicio_obj = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                        except ValueError:
                            messages.error(request, 'Data de inicio invalida.')
                            transaction.set_rollback(True)
                            return redirect('detalhe_admissao', pk=pk)
                    
                    colab = Colaborador(
                        nome=admissao.candidato_nome,
                        cpf=cpf,
                        email=admissao.candidato_email,
                        telefone=admissao.candidato_telefone or '',
                        cargo=admissao.vaga_nome,
                        unidade=admissao.unidade_destino,
                        data_admissao=data_inicio_obj,
                        status='ativo',
                    )
                    try:
                        colab.full_clean()
                        colab.save()
                    except ValidationError as exc:
                        messages.error(request, '; '.join(exc.messages))
                        transaction.set_rollback(True)
                        return redirect('detalhe_admissao', pk=pk)
                    admissao.colaborador = colab
                    admissao.data_inicio = data_inicio_obj
                messages.success(request,
                    f'🎉 Processo admissional de {admissao.candidato_nome} CONCLUÍDO! '
                    f'Colaborador liberado para a unidade.')
            else:
                messages.success(request,
                    f'✅ Status atualizado para: {admissao.get_status_display()}')
            admissao.save()
        else:
            messages.error(request, 'Transicao de status invalida para este processo.')

        return redirect('detalhe_admissao', pk=pk)


@login_required
def lista_colaboradores(request):
    colaboradores = Colaborador.objects.com_status_documental()
    total_ativos = colaboradores.filter(status='ativo').count()
    documentos_incompletos = Colaborador.objects.exclude(
        status__in=['inativo', 'desligado']
    ).com_documentacao_incompleta().count()
    status_filter = request.GET.get('status', 'ativo').strip()
    status_validos = {valor for valor, _ in Colaborador.STATUS}
    if status_filter != 'todos' and status_filter not in status_validos:
        status_filter = 'ativo'
    if status_filter != 'todos':
        colaboradores = colaboradores.filter(status=status_filter)
    documentos_filter = request.GET.get('documentos', '').strip()
    if documentos_filter not in {'', 'incompletos', 'completos'}:
        documentos_filter = ''
    if documentos_filter:
        colaboradores = colaboradores.exclude(status__in=['inativo', 'desligado'])
        colaboradores = colaboradores.filter(
            documentacao_incompleta=documentos_filter == 'incompletos'
        )
    categoria_filter = request.GET.get('categoria', '').strip()
    categorias_validas = {valor for valor, _ in Colaborador.CATEGORIAS_TRABALHO}
    if categoria_filter in categorias_validas:
        colaboradores = colaboradores.filter(categoria_trabalho=categoria_filter)
    else:
        categoria_filter = ''
    query = request.GET.get('q', '').strip()[:100]
    if query:
        filtros = (
            Q(nome__icontains=query)
            | Q(cpf__icontains=query)
            | Q(email__icontains=query)
            | Q(cargo__icontains=query)
            | Q(setor__icontains=query)
            | Q(unidade__icontains=query)
            | Q(contrato__icontains=query)
        )
        if query.isdigit():
            filtros |= Q(pk=int(query))
        colaboradores = colaboradores.filter(filtros)

    return render(request, 'admissional/lista_colaboradores.html', {
        'colaboradores': colaboradores,
        'total': colaboradores.count(),
        'total_ativos': total_ativos,
        'query': query,
        'status_filter': status_filter,
        'status_choices': Colaborador.STATUS,
        'documentos_filter': documentos_filter,
        'categoria_filter': categoria_filter,
        'categoria_choices': Colaborador.CATEGORIAS_TRABALHO,
        'total_fixos': Colaborador.objects.filter(status='ativo', categoria_trabalho='fixo').count(),
        'total_freelancers': Colaborador.objects.filter(status='ativo', categoria_trabalho='freelancer').count(),
        'documentos_incompletos': documentos_incompletos,
        'can_add_colaborador': user_has_access(
            request.user,
            permission='admissional.add_colaborador',
            profiles=('rh', 'sesmet'),
        ),
        'can_edit_colaborador': user_has_access(
            request.user,
            permission='admissional.change_colaborador',
            profiles=('rh', 'sesmet'),
        ),
        'can_view_documentos': user_has_access(
            request.user,
            permission='admissional.view_colaborador',
            profiles=('rh', 'sesmet', 'financeiro', 'gestor'),
        ),
        'can_delete_colaborador': user_has_access(
            request.user,
            permission='admissional.delete_colaborador',
            profiles=('rh',),
        ),
        'can_add_pagamento': user_has_access(
            request.user,
            permission='admissional.add_pagamentocolaborador',
            profiles=('rh', 'financeiro', 'gestor'),
        ),
    })


def _periodo_pagamentos(request):
    hoje = timezone.localdate()
    inicio_padrao = hoje.replace(day=1)
    fim_padrao = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    inicio = parse_date(request.GET.get('data_inicio', '')) or inicio_padrao
    fim = parse_date(request.GET.get('data_fim', '')) or fim_padrao
    if fim < inicio:
        inicio, fim = fim, inicio
    return inicio, fim


def _pagamentos_no_periodo(queryset, inicio, fim):
    return queryset.filter(
        Q(data_pagamento__range=(inicio, fim))
        | Q(data_pagamento__isnull=True, data_vencimento__range=(inicio, fim))
    )


def _resumo_pendencias_pagamentos(queryset, inicio, fim):
    tipos = ('salario', 'vale_transporte', 'ajuda_custo')
    valores = list(
        queryset.filter(status='pendente', tipo__in=tipos)
        .values('data_vencimento', 'tipo')
        .annotate(total=Sum('valor'), quantidade=Count('pk'))
        .order_by('data_vencimento', 'tipo')
    )

    total_meses = (fim.year - inicio.year) * 12 + fim.month - inicio.month + 1
    if total_meses <= 36:
        meses = []
        cursor = date(inicio.year, inicio.month, 1)
        limite = date(fim.year, fim.month, 1)
        while cursor <= limite:
            meses.append(cursor)
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
    else:
        meses = sorted({
            date(item['data_vencimento'].year, item['data_vencimento'].month, 1)
            for item in valores
        }) or [date(inicio.year, inicio.month, 1)]

    def linha_base(**campos):
        return {
            **campos,
            'salario': Decimal('0'),
            'vale_transporte': Decimal('0'),
            'ajuda_custo': Decimal('0'),
            'total': Decimal('0'),
            'quantidade': 0,
        }

    mensais = {
        (mes.year, mes.month): linha_base(mes=mes)
        for mes in meses
    }
    semanais = {}
    for mes in meses:
        ultimo_dia = monthrange(mes.year, mes.month)[1]
        for numero, dia_inicio in enumerate((1, 8, 15, 22), start=1):
            dia_fim = (7, 14, 21, ultimo_dia)[numero - 1]
            semanais[(mes.year, mes.month, numero)] = linha_base(
                mes=mes,
                numero=numero,
                inicio=date(mes.year, mes.month, dia_inicio),
                fim=date(mes.year, mes.month, dia_fim),
            )

    totais = linha_base()
    for item in valores:
        vencimento = item['data_vencimento']
        valor = item['total'] or Decimal('0')
        quantidade = item['quantidade'] or 0
        numero_semana = min(((vencimento.day - 1) // 7) + 1, 4)
        chave_mes = (vencimento.year, vencimento.month)
        chave_semana = (*chave_mes, numero_semana)
        for destino in (mensais[chave_mes], semanais[chave_semana], totais):
            destino[item['tipo']] += valor
            destino['total'] += valor
            destino['quantidade'] += quantidade

    return {
        'mensais': list(mensais.values()),
        'semanais': list(semanais.values()),
        **totais,
    }


def _anexar_dias_trabalhados(pagamentos, inicio, fim):
    pagamentos = list(pagamentos)
    ids = {pagamento.colaborador_id for pagamento in pagamentos}
    presencas = {
        item['colaborador_id']: item
        for item in (
        PresencaDiaria.objects.filter(
            colaborador_id__in=ids,
            data__range=(inicio, fim),
        ).values('colaborador_id').annotate(
            total_registros=Count('pk'),
            total_presentes=Count('pk', filter=Q(status='presente')),
        )
        )
    }
    for pagamento in pagamentos:
        pix = pagamento.chave_pix
        dias = pagamento.dias_trabalhados
        item_fiscal = getattr(pagamento, 'item_fiscal', None)
        if item_fiscal is not None:
            if dias is None:
                dias = item_fiscal.dias_trabalhados
            if not pix:
                pix = item_fiscal.pix
        parcela_fiscal = getattr(pagamento, 'parcela_fiscal', None)
        if not pix and parcela_fiscal is not None:
            pix = parcela_fiscal.beneficio.pix
        if dias is None:
            resumo = presencas.get(pagamento.colaborador_id)
            dias = resumo['total_presentes'] if resumo else None
        pagamento.dias_trabalhados_exibicao = dias
        pagamento.chave_pix_exibicao = pix
    return pagamentos


@login_required
@access_required(
    permission='admissional.view_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
def lista_pagamentos_colaboradores(request):
    pagamentos_base = PagamentoColaborador.objects.select_related(
        'colaborador', 'criado_por', 'item_fiscal', 'parcela_fiscal__beneficio'
    ).prefetch_related('arquivos_importados')
    pagamentos_base = pagamentos_base.exclude(
        colaborador__status__in=Colaborador.STATUS_SEM_PAGAMENTO
    )
    data_inicio, data_fim = _periodo_pagamentos(request)
    pagamentos_base = _pagamentos_no_periodo(
        pagamentos_base, data_inicio, data_fim
    )

    query = request.GET.get('q', '').strip()[:100]
    if query:
        pagamentos_base = pagamentos_base.filter(
            Q(colaborador__nome__icontains=query)
            | Q(colaborador__cpf__icontains=query)
            | Q(colaborador__unidade__icontains=query)
        )

    categoria_filter = request.GET.get('categoria', '').strip()
    categorias_validas = {valor for valor, _ in Colaborador.CATEGORIAS_TRABALHO}
    if categoria_filter in categorias_validas:
        pagamentos_base = pagamentos_base.filter(
            colaborador__categoria_trabalho=categoria_filter
        )
    else:
        categoria_filter = ''

    resumo_pendencias = _resumo_pendencias_pagamentos(
        pagamentos_base, data_inicio, data_fim
    )
    pagamentos = pagamentos_base
    status_filter = request.GET.get('status', '').strip()
    status_validos = {valor for valor, _ in PagamentoColaborador.STATUS}
    if status_filter in status_validos:
        pagamentos = pagamentos.filter(status=status_filter)
    else:
        status_filter = ''
        pagamentos = pagamentos.exclude(status='cancelado')

    tipo_filter = request.GET.get('tipo', '').strip()
    tipos_validos = {valor for valor, _ in PagamentoColaborador.TIPOS}
    if tipo_filter in tipos_validos:
        pagamentos = pagamentos.filter(tipo=tipo_filter)
    else:
        tipo_filter = ''

    totais = pagamentos.values('status').annotate(total=Sum('valor'))
    totais_status = {item['status']: item['total'] for item in totais}
    pagamentos = _anexar_dias_trabalhados(pagamentos, data_inicio, data_fim)
    return render(request, 'admissional/lista_pagamentos.html', {
        'pagamentos': pagamentos,
        'query': query,
        'status_filter': status_filter,
        'tipo_filter': tipo_filter,
        'categoria_filter': categoria_filter,
        'categoria_choices': Colaborador.CATEGORIAS_TRABALHO,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'status_choices': PagamentoColaborador.STATUS,
        'tipo_choices': PagamentoColaborador.TIPOS,
        'total_pendente': totais_status.get('pendente', 0),
        'total_pago': totais_status.get('pago', 0),
        'resumo_pendencias': resumo_pendencias,
        'can_add_pagamento': user_has_access(
            request.user,
            permission='admissional.add_pagamentocolaborador',
            profiles=('rh', 'financeiro', 'gestor'),
        ),
        'can_edit_pagamento': user_has_access(
            request.user,
            permission='admissional.change_pagamentocolaborador',
            profiles=('rh', 'financeiro', 'gestor'),
        ),
        'can_view_financeiro': user_has_access(
            request.user,
            permission='financeiro.view_documentofinanceiro',
            profiles=('financeiro', 'gestor'),
        ),
    })


@login_required
@access_required(
    permission='admissional.view_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
def visao_beneficios_colaboradores(request):
    data_inicio, data_fim = _periodo_pagamentos(request)
    pagamentos = _pagamentos_no_periodo(
        PagamentoColaborador.objects.filter(
            tipo__in=['vale_transporte', 'ajuda_custo', 'auxilio_telefonia']
        ).exclude(
            status='cancelado'
        ).exclude(
            colaborador__status__in=Colaborador.STATUS_SEM_PAGAMENTO
        ).select_related(
            'colaborador', 'item_fiscal', 'parcela_fiscal__beneficio'
        ),
        data_inicio,
        data_fim,
    )
    query = request.GET.get('q', '').strip()[:100]
    if query:
        pagamentos = pagamentos.filter(
            Q(colaborador__nome__icontains=query)
            | Q(colaborador__unidade__icontains=query)
            | Q(colaborador__cpf__icontains=query)
        )
    unidade_filter = request.GET.get('unidade', '').strip()[:100]
    if unidade_filter:
        pagamentos = pagamentos.filter(colaborador__unidade=unidade_filter)
    totais_tipo = {
        item['tipo']: item['total']
        for item in pagamentos.values('tipo').annotate(total=Sum('valor'))
    }
    total_geral = pagamentos.aggregate(total=Sum('valor'))['total'] or 0
    pessoas = pagamentos.values('colaborador_id').distinct().count()
    pagamentos = _anexar_dias_trabalhados(pagamentos, data_inicio, data_fim)
    unidades = Colaborador.objects.exclude(
        status__in=Colaborador.STATUS_SEM_PAGAMENTO
    ).exclude(unidade='').order_by('unidade').values_list(
        'unidade', flat=True
    ).distinct()
    return render(request, 'admissional/visao_beneficios.html', {
        'pagamentos': pagamentos,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'query': query,
        'unidade_filter': unidade_filter,
        'unidades': unidades,
        'total_vt': totais_tipo.get('vale_transporte', 0),
        'total_ajuda': totais_tipo.get('ajuda_custo', 0),
        'total_geral': total_geral,
        'total_pessoas': pessoas,
    })


@login_required
@access_required(
    permission='admissional.view_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
def resumo_colaborador_pagamento(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    inicio, fim = _periodo_pagamentos(request)
    presencas = PresencaDiaria.objects.filter(
        colaborador=colaborador,
        data__range=(inicio, fim),
    )
    dias_trabalhados = presencas.filter(status='presente').count()
    return JsonResponse({
        'nome': colaborador.nome,
        'categoria': colaborador.get_categoria_trabalho_display(),
        'tipo_contrato': colaborador.get_tipo_contrato_display(),
        'dias_trabalhados': dias_trabalhados if presencas.exists() else None,
        'periodo': f'{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}',
    })


@login_required
@access_required(
    permission='admissional.add_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
def novo_pagamento_colaborador(request):
    if request.method == 'POST':
        form = PagamentoColaboradorForm(request.POST)
        if form.is_valid():
            pagamento = form.save(commit=False)
            pagamento.criado_por = request.user
            pagamento.save()
            _, recorrencia_criada = pagamento.criar_proxima_recorrencia(request.user)
            mensagem = 'Pagamento cadastrado com sucesso.'
            if recorrencia_criada:
                mensagem += ' A próxima semana foi gerada automaticamente.'
            messages.success(request, mensagem)
            return redirect('lista_pagamentos_colaboradores')
    else:
        initial = {
            'colaborador': request.GET.get('colaborador', ''),
            'tipo': request.GET.get('tipo', ''),
            'status': 'pendente',
        }
        hoje = timezone.localdate()
        if initial['tipo'] in {'vale_transporte', 'ajuda_custo'}:
            segunda = hoje - timedelta(days=hoje.weekday())
            initial.update({
                'competencia': segunda,
                'competencia_fim': segunda + timedelta(days=6),
                'data_vencimento': segunda,
                'recorrente': True,
            })
        else:
            initial.update({
                'competencia': hoje.replace(day=1),
                'competencia_fim': hoje.replace(day=monthrange(hoje.year, hoje.month)[1]),
            })
        colaborador_id = str(initial['colaborador']).strip()
        if colaborador_id.isdigit() and initial['tipo'] in {'salario', 'vale_transporte', 'ajuda_custo'}:
            colaborador = Colaborador.objects.filter(pk=colaborador_id).first()
            if colaborador:
                if initial['tipo'] == 'salario':
                    campo_valor = 'salario'
                elif initial['tipo'] == 'vale_transporte':
                    campo_valor = 'vale_transporte_semanal'
                else:
                    campo_valor = 'ajuda_custo_semanal'
                initial['valor'] = getattr(colaborador, campo_valor)
        form = PagamentoColaboradorForm(initial=initial)
    return render(request, 'admissional/form_pagamento.html', {
        'form': form,
        'acao': 'Novo pagamento',
    })


@login_required
@access_required(
    permission='admissional.change_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
def editar_pagamento_colaborador(request, pk):
    pagamento = get_object_or_404(PagamentoColaborador, pk=pk)
    if request.method == 'POST':
        form = PagamentoColaboradorForm(request.POST, instance=pagamento)
        if form.is_valid():
            pagamento = form.save()
            _, recorrencia_criada = pagamento.criar_proxima_recorrencia(request.user)
            mensagem = 'Pagamento atualizado com sucesso.'
            if recorrencia_criada:
                mensagem += ' A próxima semana foi gerada automaticamente.'
            messages.success(request, mensagem)
            return redirect('lista_pagamentos_colaboradores')
    else:
        form = PagamentoColaboradorForm(instance=pagamento)
    return render(request, 'admissional/form_pagamento.html', {
        'form': form,
        'acao': 'Editar pagamento',
        'pagamento': pagamento,
    })


@login_required
@require_POST
@access_required(
    permission='admissional.change_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
@transaction.atomic
def marcar_pagamento_como_pago(request, pk):
    pagamento = get_object_or_404(
        PagamentoColaborador.objects.select_for_update(), pk=pk
    )
    if pagamento.status == 'cancelado':
        messages.error(request, 'Este lançamento foi retirado da folha e não pode ser pago.')
    elif pagamento.status == 'pago':
        messages.info(request, 'Este pagamento já estava marcado como pago.')
    else:
        pagamento.status = 'pago'
        pagamento.data_pagamento = timezone.localdate()
        pagamento.save(update_fields=['status', 'data_pagamento', 'atualizado_em'])
        _, recorrencia_criada = pagamento.criar_proxima_recorrencia(request.user)
        mensagem = 'Pagamento marcado como pago.'
        if recorrencia_criada:
            mensagem += ' A próxima semana foi gerada automaticamente.'
        messages.success(request, mensagem)
    return redirect('lista_pagamentos_colaboradores')


@login_required
@require_POST
@access_required(
    permission='admissional.change_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
@transaction.atomic
def retirar_pagamento_folha(request, pk):
    pagamento = get_object_or_404(
        PagamentoColaborador.objects.select_for_update(), pk=pk
    )
    if pagamento.status == 'pago':
        messages.error(
            request,
            'Pagamento já realizado não pode ser retirado da folha. Use uma correção auditável.',
        )
    elif pagamento.status == 'cancelado':
        messages.info(request, 'Este lançamento já estava fora da folha.')
    else:
        pagamento.status = 'cancelado'
        pagamento.recorrente = False
        pagamento.save(update_fields=['status', 'recorrente', 'atualizado_em'])
        messages.success(request, 'Lançamento retirado da folha sem apagar o histórico.')
    return redirect('lista_pagamentos_colaboradores')

@login_required
@access_required(permission='admissional.add_colaborador', profiles=('rh', 'sesmet'))
@transaction.atomic
def novo_colaborador(request):
    if request.method == 'POST':
        form = ColaboradorForm(request.POST, request.FILES, require_document=True)
        if form.is_valid():
            try:
                for field_name in form.fields:
                    if field_name.startswith('anexo_'):
                        assign_direct_upload(form.instance, request, field_name)
                colaborador = form.save()
            except ValidationError as exc:
                transaction.set_rollback(True)
                form.add_error(None, exc.messages[0])
                return render(request, 'admissional/form_colaborador.html', {
                    'form': form, 'acao': 'Novo', 'exige_documento': True,
                })
            except OSError:
                transaction.set_rollback(True)
                form.add_error(None, 'Nao foi possivel armazenar os anexos. Tente novamente.')
                return render(request, 'admissional/form_colaborador.html', {
                    'form': form, 'acao': 'Novo', 'exige_documento': True,
                })
            identificacao = colaborador.nome or f'#{colaborador.pk}'
            messages.success(request, f'Colaborador {identificacao} cadastrado com sucesso!')
            return redirect('documentos_colaborador', pk=colaborador.pk)
    else:
        form = ColaboradorForm(require_document=True)
    return render(request, 'admissional/form_colaborador.html', {
        'form': form, 'acao': 'Novo', 'exige_documento': True,
    })

@login_required
@access_required(permission='admissional.change_colaborador', profiles=('rh', 'sesmet'))
@transaction.atomic
def editar_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    if request.method == 'POST':
        form = ColaboradorForm(request.POST, request.FILES, instance=colaborador)
        if form.is_valid():
            try:
                for field_name in form.fields:
                    if field_name.startswith('anexo_'):
                        assign_direct_upload(form.instance, request, field_name)
                form.save()
            except ValidationError as exc:
                transaction.set_rollback(True)
                form.add_error(None, exc.messages[0])
                return render(request, 'admissional/form_colaborador.html', {'form': form, 'acao': 'Editar'})
            except OSError:
                transaction.set_rollback(True)
                form.add_error(None, 'Nao foi possivel armazenar os anexos. Tente novamente.')
                return render(request, 'admissional/form_colaborador.html', {'form': form, 'acao': 'Editar'})
            messages.success(request, f'Colaborador {colaborador.nome} atualizado com sucesso!')
            return redirect('lista_colaboradores')
    else:
        form = ColaboradorForm(instance=colaborador)
    return render(request, 'admissional/form_colaborador.html', {'form': form, 'acao': 'Editar'})


@login_required
@access_required(
    permission='admissional.view_colaborador',
    profiles=('rh', 'sesmet', 'financeiro', 'gestor'),
)
@transaction.atomic
def documentos_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    pode_editar_documentos = user_has_access(
        request.user,
        permission='admissional.change_colaborador',
        profiles=('rh', 'sesmet', 'gestor'),
    )
    if request.method == 'POST':
        if not pode_editar_documentos:
            raise PermissionDenied
        tipo = request.POST.get('tipo', '').strip()
        descricao = request.POST.get('descricao', '').strip()[:255]
        data_texto = request.POST.get('data_referencia', '').strip()
        data_referencia = parse_date(data_texto) if data_texto else None
        tipos_validos = {value for value, _label in DocumentoColaborador.TIPOS}
        arquivo_upload = request.FILES.get('arquivo_colaborador')

        if tipo not in tipos_validos:
            messages.error(request, 'Selecione um tipo de documento válido.')
        elif tipo == 'ajuda_custo' and not data_referencia:
            messages.error(request, 'Informe a semana de referência da ajuda de custo.')
        else:
            try:
                direct_key = verify_direct_upload(request, 'arquivo_colaborador')
                if arquivo_upload:
                    validate_document_upload(arquivo_upload)
                if not arquivo_upload and not direct_key:
                    raise ValidationError('Selecione um arquivo PDF, PNG ou JPG.')

                documento = DocumentoColaborador(
                    colaborador=colaborador,
                    tipo=tipo,
                    data_referencia=data_referencia,
                    descricao=descricao,
                    enviado_por=request.user,
                )
                if arquivo_upload:
                    documento.arquivo = arquivo_upload
                    documento.nome_original = get_valid_filename(arquivo_upload.name)[:255]
                else:
                    documento.arquivo.name = direct_key
                    nome_enviado = request.POST.get('nome_original', '').strip()
                    documento.nome_original = get_valid_filename(nome_enviado)[:255]
                documento.full_clean()
                documento.save()
            except (ValidationError, OSError) as exc:
                mensagem = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                messages.error(request, mensagem or 'Não foi possível salvar o documento.')
            else:
                messages.success(request, 'Documento anexado ao colaborador com sucesso.')
                return redirect('documentos_colaborador', pk=colaborador.pk)

    documentos = colaborador.documentos_arquivo.select_related('enviado_por')
    campos_anexo = (
        ('anexo_cpf', 'CPF/CNPJ — frente'),
        ('anexo_cpf_verso', 'CPF/CNPJ — verso'),
        ('anexo_rg', 'RG — frente'),
        ('anexo_rg_verso', 'RG — verso'),
        ('anexo_pis', 'PIS/PASEP — frente'),
        ('anexo_pis_verso', 'PIS/PASEP — verso'),
        ('anexo_ctps', 'CTPS — frente'),
        ('anexo_ctps_verso', 'CTPS — verso'),
        ('anexo_titulo', 'Título de eleitor — frente'),
        ('anexo_titulo_verso', 'Título de eleitor — verso'),
        ('anexo_reservista', 'Reservista — frente'),
        ('anexo_reservista_verso', 'Reservista — verso'),
        ('anexo_aso', 'ASO'),
    )
    anexos_cadastrais = [
        {'campo': campo, 'label': label, 'arquivo': getattr(colaborador, campo)}
        for campo, label in campos_anexo
        if getattr(colaborador, campo)
    ]
    pode_ver_pagamentos = user_has_access(
        request.user,
        permission='admissional.view_pagamentocolaborador',
        profiles=('rh', 'financeiro', 'gestor'),
    )
    pagamentos_documentados = []
    arquivos_central_colaborador = []
    if pode_ver_pagamentos:
        pagamentos_documentados = colaborador.pagamentos.filter(
            arquivos_importados__isnull=False
        ).prefetch_related('arquivos_importados').distinct()
        arquivos_central_colaborador = ArquivoImportado.objects.filter(
            content_type=ContentType.objects.get_for_model(Colaborador),
            object_id=colaborador.pk,
        ).prefetch_related('origens')

    pode_ver_fiscal = user_has_access(
        request.user,
        permission='fiscal.view_folhafiscal',
        profiles=('financeiro', 'gestor'),
    )
    folhas_fiscais = []
    if pode_ver_fiscal:
        from fiscal.models import FolhaFiscal
        folhas_fiscais = FolhaFiscal.objects.filter(
            Q(itens__colaborador=colaborador)
            | Q(beneficios__colaborador=colaborador)
        ).select_related('arquivo_origem').distinct()
    return render(request, 'admissional/documentos_colaborador.html', {
        'colaborador': colaborador,
        'documentos': documentos,
        'anexos_cadastrais': anexos_cadastrais,
        'pagamentos_documentados': pagamentos_documentados,
        'arquivos_central_colaborador': arquivos_central_colaborador,
        'folhas_fiscais': folhas_fiscais,
        'tipos_documento': DocumentoColaborador.TIPOS,
        'pode_editar_documentos': pode_editar_documentos,
        'pode_ver_pagamentos': pode_ver_pagamentos,
        'pode_ver_fiscal': pode_ver_fiscal,
    })


@login_required
@access_required(
    permission='admissional.view_colaborador',
    profiles=('rh', 'sesmet', 'financeiro', 'gestor'),
)
def baixar_anexo_colaborador(request, pk, campo):
    campos_permitidos = {
        'anexo_cpf', 'anexo_cpf_verso', 'anexo_rg', 'anexo_rg_verso',
        'anexo_pis', 'anexo_pis_verso', 'anexo_ctps', 'anexo_ctps_verso',
        'anexo_titulo', 'anexo_titulo_verso', 'anexo_reservista',
        'anexo_reservista_verso', 'anexo_aso',
    }
    if campo not in campos_permitidos:
        raise Http404
    colaborador = get_object_or_404(Colaborador, pk=pk)
    arquivo = getattr(colaborador, campo)
    if not arquivo:
        raise Http404
    return redirect(arquivo.url)


@login_required
@access_required(
    permission='admissional.view_colaborador',
    profiles=('rh', 'sesmet', 'financeiro', 'gestor'),
)
def baixar_documento_colaborador(request, pk, documento_pk):
    documento = get_object_or_404(
        DocumentoColaborador, pk=documento_pk, colaborador_id=pk
    )
    return redirect(documento.arquivo.url)


@login_required
@require_POST
@access_required(permission='admissional.change_colaborador', profiles=('rh', 'sesmet', 'gestor'))
@transaction.atomic
def excluir_documento_colaborador(request, pk, documento_pk):
    documento = get_object_or_404(
        DocumentoColaborador, pk=documento_pk, colaborador_id=pk
    )
    documento.delete()
    messages.success(request, 'Documento removido do colaborador.')
    return redirect('documentos_colaborador', pk=pk)

@login_required
@access_required(permission='admissional.delete_colaborador', profiles=('rh',))
def excluir_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    if request.method == 'POST':
        nome = colaborador.nome
        # Desativacao logica: preserva cadastro, documentos e todo o historico.
        colaborador.status = 'inativo'
        colaborador.save(update_fields=['status'])
        messages.success(
            request,
            f'Colaborador {nome} desativado com sucesso. Os próximos pagamentos '
            'recorrentes saíram da folha; nenhum histórico foi excluído.'
        )
        return redirect(f"{reverse('lista_colaboradores')}?status=inativo")
    return render(request, 'admissional/excluir_colaborador.html', {'colaborador': colaborador})


@login_required
@require_POST
@access_required(permission='admissional.delete_colaborador', profiles=('rh',))
def reativar_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk, status='inativo')
    colaborador.status = 'ativo'
    colaborador.save(update_fields=['status'])
    messages.success(request, f'Colaborador {colaborador.nome} reativado com sucesso.')
    return redirect('lista_colaboradores')


@login_required
def baixar_documento(request, admissao_pk, doc_pk):
    from django.http import HttpResponse, HttpResponseNotFound
    
    admissao = get_object_or_404(Admissao, pk=admissao_pk)
    doc = get_object_or_404(DocumentoAdmissional, pk=doc_pk, admissao=admissao)
    
    if doc.arquivo_nuvem:
        return redirect(doc.arquivo_nuvem.url)
        
    if doc.arquivo:
        content_type = doc.arquivo_mimetype or 'application/octet-stream'
        filename = get_valid_filename(doc.arquivo_nome or f'documento_{doc.get_tipo_display()}.bin')
        
        response = HttpResponse(doc.arquivo, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    return HttpResponseNotFound("Arquivo não encontrado.")


import csv
from django.http import HttpResponse
from datetime import timedelta
from .models import PresencaDiaria

@login_required
@access_required(permission='admissional.change_presencadiaria', profiles=('rh',))
@transaction.atomic
def controle_presenca(request):
    from datetime import datetime
    data_str = request.GET.get('data') or request.POST.get('data')
    unidade_filter = (
        request.GET.get('unidade') or request.POST.get('unidade') or ''
    ).strip()[:100]
    
    if data_str:
        try:
            data_selecionada = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data_selecionada = timezone.now().date()
    else:
        data_selecionada = timezone.now().date()
        
    if request.method == 'POST':
        status_validos = {choice[0] for choice in PresencaDiaria.STATUS_CHOICES}
        colaboradores_validos = set(
            Colaborador.objects.filter(status='ativo').values_list('pk', flat=True)
        )
        for key, value in request.POST.items():
            if key.startswith('colaborador_'):
                try:
                    colab_pk = int(key.split('_')[1])
                except (ValueError, IndexError):
                    continue
                status = request.POST.get(f'status_{colab_pk}')
                obs = request.POST.get(f'obs_{colab_pk}', '')
                if colab_pk not in colaboradores_validos or status not in status_validos:
                    continue
                
                PresencaDiaria.objects.update_or_create(
                    colaborador_id=colab_pk,
                    data=data_selecionada,
                    defaults={'status': status, 'observacao': obs}
                )
        messages.success(request, f'Presenças salvas com sucesso para o dia {data_selecionada.strftime("%d/%m/%Y")}!')
        query = urlencode({'data': data_selecionada.isoformat(), 'unidade': unidade_filter})
        return redirect(f'{request.path}?{query}')

    colaboradores = Colaborador.objects.filter(status='ativo')
    if unidade_filter:
        colaboradores = colaboradores.filter(unidade__icontains=unidade_filter)
        
    colaboradores = list(colaboradores)
    registros = {
        presenca.colaborador_id: presenca
        for presenca in PresencaDiaria.objects.filter(
            colaborador_id__in=[c.pk for c in colaboradores],
            data=data_selecionada,
        )
    }
    presencas = [
        registros.get(c.pk) or PresencaDiaria(colaborador=c, data=data_selecionada)
        for c in colaboradores
    ]
    total_nao_definidos = sum(p.status == 'indefinido' for p in presencas)
        
    return render(request, 'admissional/controle_presenca.html', {
        'presencas': presencas,
        'data_selecionada': data_selecionada,
        'unidade_filter': unidade_filter,
        'status_choices': PresencaDiaria.STATUS_CHOICES,
        'total_nao_definidos': total_nao_definidos,
        'total_definidos': len(presencas) - total_nao_definidos,
        'total_colaboradores_presenca': len(presencas),
    })

@login_required
def exportar_presenca_csv(request):
    data_str = request.GET.get('data')
    unidade_filter = request.GET.get('unidade', '')
    from datetime import datetime
    try:
        data_filtro = datetime.strptime(data_str or '', '%Y-%m-%d').date()
    except ValueError:
        return HttpResponse('Data invalida.', status=400, content_type='text/plain')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="presenca_{data_str}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Data', 'Colaborador', 'CPF/Matricula', 'Cliente/Unidade', 'Cidade/UF', 'Status', 'Observacao'])
    
    colaboradores = Colaborador.objects.filter(status='ativo')
    if unidade_filter:
        colaboradores = colaboradores.filter(unidade__icontains=unidade_filter)
    colaboradores = list(colaboradores)
    presencas = {
        p.colaborador_id: p
        for p in PresencaDiaria.objects.filter(
            data=data_filtro,
            colaborador_id__in=[c.pk for c in colaboradores],
        )
    }

    for colaborador in colaboradores:
        p = presencas.get(colaborador.pk)
        def csv_safe(value):
            text = str(value or '')
            return "'" + text if text.startswith(('=', '+', '-', '@')) else text

        writer.writerow([
            data_filtro.strftime("%d/%m/%Y"),
            csv_safe(colaborador.nome),
            csv_safe(colaborador.cpf),
            csv_safe(colaborador.unidade),
            '',
            p.get_status_display() if p else 'Não definido',
            csv_safe(p.observacao if p else ''),
        ])
    return response

@login_required
def periodo_experiencia(request):
    colaboradores = Colaborador.objects.filter(status='ativo', data_admissao__isnull=False)
    hoje = timezone.now().date()
    
    for c in colaboradores:
        try:
            if isinstance(c.data_admissao, str):
                from datetime import datetime
                c.data_admissao = datetime.strptime(c.data_admissao, '%Y-%m-%d').date()
            if c.data_admissao:
                c.data_45 = c.data_admissao + timedelta(days=45)
                c.data_90 = c.data_admissao + timedelta(days=90)
                c.dias_45_restantes = (c.data_45 - hoje).days
                c.dias_90_restantes = (c.data_90 - hoje).days
            else:
                c.data_45 = hoje
                c.data_90 = hoje
                c.dias_45_restantes = 0
                c.dias_90_restantes = 0
        except Exception:
            c.data_45 = hoje
            c.data_90 = hoje
            c.dias_45_restantes = 0
            c.dias_90_restantes = 0
        
    return render(request, 'admissional/experiencia_dashboard.html', {
        'colaboradores': colaboradores,
    })
