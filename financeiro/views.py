"""ERP Grupo PremiumBR — Views do Módulo 6: Financeiro / Fiscal"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.db.models import Q, Sum
from django.db import transaction
import logging
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from .models import DocumentoFinanceiro, AuditoriaItem, LancamentoERP, OrcamentoCentroCusto, ItemDocumentoFinanceiro
from django.http import HttpResponse
from django.core.files.storage import default_storage
from core.access import access_required, user_has_access
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST, require_http_methods
from .forms import PagamentoDocumentoForm, CancelamentoDocumentoForm, DetalhamentoDocumentoForm
from core.validators import validate_document_upload, validate_pdf_upload
from core.direct_uploads import verify_direct_upload
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename
from admissional.models import Colaborador, PagamentoColaborador
from admissional.periodos_pagamentos import pagamentos_atuais, pagamentos_atrasados
from core.models import AprovacaoRegistro, ArquivoImportado
from core.payment_approvals import (
    sincronizar_aprovacao_pagamento, exigir_aprovacao_pagamento,
    situacao_aprovacao_pagamento,
)


logger = logging.getLogger(__name__)


@login_required
def painel_financeiro(request):
    pagamentos = DocumentoFinanceiro.objects.exclude(status='cancelado')
    fluxos = {
        'saidas': ('a_pagar', 'pago'),
        'entradas': ('a_receber', 'recebido'),
        'classificar': ('nao_informado',),
    }
    fluxo = request.GET.get('fluxo', '' if request.GET.get('pagamento') else 'saidas')
    if fluxo in fluxos:
        pagamentos = pagamentos.filter(situacao_pagamento__in=fluxos[fluxo])
    else:
        fluxo = ''
    resumo_contas = DocumentoFinanceiro.objects.exclude(status='cancelado').aggregate(
        a_pagar=Sum('valor', filter=Q(situacao_pagamento='a_pagar')),
        a_receber=Sum('valor', filter=Q(situacao_pagamento='a_receber')),
    )
    filtro_pagamento = request.GET.get('pagamento', '')
    if filtro_pagamento == 'cancelado':
        pagamentos = DocumentoFinanceiro.objects.filter(status='cancelado')
    elif filtro_pagamento in dict(DocumentoFinanceiro.SITUACOES_PAGAMENTO):
        pagamentos = pagamentos.filter(situacao_pagamento=filtro_pagamento)
    else:
        filtro_pagamento = ''
    pagina_pagamentos = Paginator(pagamentos, 20).get_page(request.GET.get('pagina'))
    for documento in pagina_pagamentos:
        if documento.situacao_pagamento == 'a_pagar':
            documento.situacao_aprovacao = situacao_aprovacao_pagamento(documento)
    docs_pendentes = DocumentoFinanceiro.objects.filter(status__in=['recebido', 'em_auditoria'])
    lancamentos_pendentes = LancamentoERP.objects.filter(status__in=['rascunho', 'em_validacao'])
    finalizados_mes = LancamentoERP.objects.filter(
        status='finalizado',
        finalizado_em__month=timezone.now().month,
        finalizado_em__year=timezone.now().year,
    )
    # Calcula Orcamento/Budget do Mês
    mes_atual = timezone.localdate().replace(day=1)
    if mes_atual.month == 12:
        proximo_mes = mes_atual.replace(year=mes_atual.year + 1, month=1)
    else:
        proximo_mes = mes_atual.replace(month=mes_atual.month + 1)
    fim_mes = proximo_mes - timedelta(days=1)
    folha_base = PagamentoColaborador.objects.exclude(
        Q(colaborador__status__in=Colaborador.STATUS_SEM_PAGAMENTO) & ~Q(tipo='distrato')
    )
    folha_mes = pagamentos_atuais(folha_base, timezone.localdate())
    folha_atrasada = pagamentos_atrasados(folha_base, timezone.localdate())
    resumo_folha = folha_mes.aggregate(
        total=Sum('valor'),
        pago=Sum('valor', filter=Q(status='pago')),
        pendente=Sum('valor', filter=Q(status='pendente')),
        beneficios=Sum(
            'valor', filter=Q(tipo__in=['vale_transporte', 'ajuda_custo', 'auxilio_telefonia'])
        ),
    )
    arquivos_area = ArquivoImportado.objects.filter(
        area__in=('financeiro', 'fiscal')
    ).prefetch_related('origens').order_by('-criado_em', '-pk')
    
    dashboard_budget = []
    try:
        orcamentos = OrcamentoCentroCusto.objects.filter(competencia=mes_atual)
        for orcamento in orcamentos:
            # Gasto real: Lançamentos finalizados desse centro de custo no mês
            gasto = LancamentoERP.objects.filter(
                centro_custo=orcamento.centro_custo,
                status='finalizado',
                finalizado_em__month=timezone.now().month,
                finalizado_em__year=timezone.now().year,
            ).aggregate(total=Sum('valor'))['total'] or 0
            
            economia_valor = orcamento.valor_orcado - gasto
            meta_valor = orcamento.valor_orcado * (orcamento.meta_reducao_custo / 100)
            atingiu_meta = economia_valor >= meta_valor

            dashboard_budget.append({
                'centro_custo': orcamento.centro_custo,
                'orcado': orcamento.valor_orcado,
                'gasto': gasto,
                'saldo': orcamento.valor_orcado - gasto,
                'meta_reducao_percentual': orcamento.meta_reducao_custo,
                'atingiu_meta': atingiu_meta
            })
    except Exception:
        logger.exception('Falha ao carregar orcamentos do painel financeiro')
        messages.error(request, 'Nao foi possivel carregar os orcamentos.')

    return render(request, 'financeiro/painel.html', {
        'pagamentos': pagina_pagamentos,
        'filtro_pagamento': filtro_pagamento,
        'fluxo': fluxo,
        'resumo_contas': resumo_contas,
        'total_classificar': DocumentoFinanceiro.objects.filter(situacao_pagamento='nao_informado').count(),
        'situacoes_pagamento': DocumentoFinanceiro.SITUACOES_PAGAMENTO,
        'docs_pendentes': docs_pendentes,
        'lancamentos_pendentes': lancamentos_pendentes,
        'finalizados_mes': finalizados_mes,
        'total_valor_pendente': sum(d.valor for d in docs_pendentes),
        'total_lancado_mes': sum(l.valor for l in finalizados_mes),
        'dashboard_budget': dashboard_budget,
        'folha_mes_quantidade': folha_mes.count(),
        'folha_atrasada_quantidade': folha_atrasada.count(),
        'folha_atrasada_total': folha_atrasada.aggregate(total=Sum('valor'))['total'] or 0,
        'folha_mes_total': resumo_folha['total'] or 0,
        'folha_mes_pago': resumo_folha['pago'] or 0,
        'folha_mes_pendente': resumo_folha['pendente'] or 0,
        'folha_mes_beneficios': resumo_folha['beneficios'] or 0,
        'arquivos_area': arquivos_area[:12],
        'total_arquivos_area': arquivos_area.count(),
    })


@login_required
@access_required(permission='financeiro.add_documentofinanceiro', profiles=('financeiro', 'gestor'))
@transaction.atomic
def entrada_documento(request):
    pagamento_form = PagamentoDocumentoForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        campos_obrigatorios = (
            'tipo', 'numero_documento', 'descricao', 'valor',
        )
        if any(not request.POST.get(campo, '').strip() for campo in campos_obrigatorios):
            messages.error(request, 'Preencha todos os campos obrigatorios.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })
        try:
            valor_documento = Decimal(request.POST['valor'].replace(',', '.'))
        except (InvalidOperation, ValueError):
            valor_documento = Decimal('-1')
        if valor_documento <= 0:
            messages.error(request, 'O valor do documento deve ser maior que zero.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })

        # Compatibilidade com integrações que ainda não enviam o novo campo.
        if 'situacao_pagamento' not in request.POST:
            dados_pagamento = request.POST.copy()
            dados_pagamento['situacao_pagamento'] = 'a_pagar'
            pagamento_form = PagamentoDocumentoForm(dados_pagamento)
        if not pagamento_form.is_valid():
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })
        if pagamento_form.cleaned_data['situacao_pagamento'] == 'pago':
            pagamento_form.add_error('situacao_pagamento', 'Cadastre como A pagar para aprovação de Luiz antes de confirmar a baixa.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })

        doc = DocumentoFinanceiro(
            **pagamento_form.cleaned_data,
            tipo=request.POST['tipo'],
            numero_documento=request.POST['numero_documento'],
            descricao=request.POST['descricao'],
            valor=valor_documento,
            centro_custo=request.POST.get('centro_custo', '').strip(),
            unidade=request.POST.get('unidade', '').strip(),
            cnpj_emitente=request.POST.get('cnpj_emitente', ''),
            razao_social_emitente=request.POST.get('razao_social_emitente', ''),
            contratos_vinculados=request.POST.get('contratos_vinculados', ''),
            data_emissao=request.POST.get('data_emissao') or None,
            data_vencimento=request.POST.get('data_vencimento') or None,
            status='em_auditoria',
            recebido_por=request.user,
        )
        
        arquivo_upload = request.FILES.get('arquivo_pdf')
        try:
            direct_key = verify_direct_upload(request, 'arquivo_pdf')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })
        if arquivo_upload:
            try:
                validate_document_upload(arquivo_upload)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'financeiro/entrada_documento.html', {
                    'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
                })
            doc.arquivo = arquivo_upload
        elif direct_key:
            doc.arquivo.name = direct_key

        try:
            doc.full_clean()
            doc.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })
        except OSError:
            transaction.set_rollback(True)
            messages.error(request, 'Nao foi possivel armazenar o documento. Tente novamente.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })

        produtos_json = request.POST.get('produtos_json', '[]')
        try:
            produtos = json.loads(produtos_json)
            if not isinstance(produtos, list) or len(produtos) > 200:
                raise ValueError('Lista de itens invalida')
            for prod in produtos:
                if not isinstance(prod, dict):
                    raise ValueError('Item invalido')
                item = ItemDocumentoFinanceiro(
                    documento=doc,
                    descricao_produto=prod.get('descricao_produto', 'Produto sem nome')[:255],
                    ncm=prod.get('ncm', '')[:20],
                    quantidade=prod.get('quantidade') or 1,
                    valor_unitario=prod.get('valor_unitario') or 0,
                    valor_total=prod.get('valor_total') or 0,
                )
                item.full_clean()
                item.save()
        except (TypeError, ValueError, json.JSONDecodeError, ValidationError):
            transaction.set_rollback(True)
            messages.error(request, 'A lista de itens do documento e invalida.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })

        # Criar checklist de auditoria automaticamente
        for item_key, _ in AuditoriaItem.ITENS_CHECKLIST:
            AuditoriaItem.objects.create(documento=doc, item=item_key, status='pendente')
        try:
            with transaction.atomic():
                sincronizar_aprovacao_pagamento(doc, request.user)
        except ValidationError as exc:
            transaction.set_rollback(True)
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
            })

        messages.info(request,
            f'📋 Documento {doc.numero_documento} recebido. Iniciando auditoria interna...')
        return redirect('auditoria_documento', pk=doc.pk)

    return render(request, 'financeiro/entrada_documento.html', {
        'tipos': DocumentoFinanceiro.TIPOS, 'pagamento_form': pagamento_form,
    })

from django.http import JsonResponse
from .services.ocr_service import extrair_dados_documento

@login_required
@access_required(
    permission='financeiro.add_documentofinanceiro',
    groups=('Financeiro_Operador', 'Financeiro_Auditor', 'Financeiro_Aprovador'),
)
def extrair_ocr_documento(request):
    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo')
        try:
            if arquivo:
                validate_document_upload(arquivo)
                file_bytes = arquivo.read()
                content_type = arquivo.content_type
            else:
                key = verify_direct_upload(request, 'arquivo_pdf', required=True)
                with default_storage.open(key, 'rb') as stored_file:
                    file_bytes = stored_file.read()
                content_type = request.POST.get('direct_upload_content_type', 'application/pdf')
            dados = extrair_dados_documento(file_bytes, content_type)
            return JsonResponse({'sucesso': True, 'dados': dados})
        except ValidationError as exc:
            return JsonResponse({'sucesso': False, 'erro': exc.messages[0]}, status=400)
        except Exception:
            logger.exception('Falha na extracao OCR')
            return JsonResponse({'sucesso': False, 'erro': 'Nao foi possivel ler o documento.'}, status=400)
    return JsonResponse({'sucesso': False, 'erro': 'Arquivo não enviado.'}, status=400)


@login_required
@access_required(
    permission='financeiro.change_documentofinanceiro',
    groups=('Financeiro_Auditor', 'Financeiro_Aprovador'),
)
@transaction.atomic
def auditoria_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=pk)
    if doc.status == 'cancelado':
        messages.error(request, 'Documento cancelado. A auditoria não pode ser alterada.')
        return redirect('detalhe_documento', pk=pk)
    if not doc.pode_auditar:
        messages.error(request, 'Documento já lançado. A auditoria que fundamentou o lançamento não pode ser alterada.')
        return redirect('detalhe_documento', pk=pk)
    # Documentos antigos ou importados podem não ter o checklist completo.
    # Reabrir a auditoria disponibiliza os itens ausentes sem aprová-los.
    for item_key, _ in AuditoriaItem.ITENS_CHECKLIST:
        AuditoriaItem.objects.get_or_create(documento=doc, item=item_key)
    itens = doc.auditoria.all()

    if request.method == 'POST':
        status_validos = {value for value, _ in AuditoriaItem.STATUS}
        if any(request.POST.get(f'item_{item.pk}', 'pendente') not in status_validos for item in itens):
            messages.error(request, 'Status de auditoria invalido.')
            return redirect('auditoria_documento', pk=pk)
        # Atualizar cada item da auditoria
        for item in itens:
            novo_status = request.POST.get(f'item_{item.pk}', 'pendente')
            obs = request.POST.get(f'obs_{item.pk}', '')
            item.status = novo_status
            item.observacao = obs
            item.verificado_por = request.user
            item.save()

        # Gateway 1: Todos os itens OK?
        todos_ok = doc.auditoria_aprovada
        tem_divergente = any(i.status == 'divergente' for i in itens)

        if tem_divergente:
            doc.status = 'informacoes_incorretas'
            doc.save()
            messages.error(request,
                '❌ GATEWAY: Auditoria reprovada! Existem divergências. '
                'Documento devolvido ao emissor para correção.')
        elif todos_ok:
            doc.status = 'aprovado_lancamento'
            doc.save()
            messages.success(request,
                '✅ GATEWAY: Auditoria aprovada! Documento liberado para lançamento no ERP.')
        else:
            doc.status = 'em_auditoria'
            doc.save(update_fields=['status', 'atualizado_em'])
            messages.warning(request, '⚠️ Auditoria parcialmente concluída. Verifique todos os itens.')

        return redirect('detalhe_documento', pk=pk)

    return render(request, 'financeiro/auditoria.html', {
        'documento': doc,
        'itens': itens,
        'status_choices': AuditoriaItem.STATUS,
    })


ACESSO_PAGAMENTO = dict(
    permission='financeiro.change_documentofinanceiro',
    profiles=('financeiro', 'gestor'),
    groups=('Financeiro_Operador', 'Financeiro_Aprovador'),
)


@login_required
@access_required(**ACESSO_PAGAMENTO)
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def cancelar_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=pk)
    aprovacoes = AprovacaoRegistro.objects.filter(
        content_type__app_label='financeiro', content_type__model='lancamentoerp',
        object_id__in=LancamentoERP.objects.filter(documento_id=pk).values('pk'),
        status='pendente',
    )
    # Bloqueia a origem antes da fila, como a decisão central.
    aprovacoes_bloqueadas = list(aprovacoes.select_for_update().values_list('pk', flat=True))
    if doc.status == 'cancelado':
        messages.info(request, 'Este documento já está cancelado.')
        return redirect('detalhe_documento', pk=pk)
    if not doc.pode_cancelar:
        messages.error(request, 'Documento pago, recebido ou finalizado. É necessário tratar o estorno antes de cancelar.')
        return redirect('detalhe_documento', pk=pk)
    form = CancelamentoDocumentoForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        if aprovacoes.exclude(pk__in=aprovacoes_bloqueadas).exists():
            messages.error(request, 'O documento recebeu um novo lançamento. Atualize a página antes de cancelar.')
            return redirect('detalhe_documento', pk=pk)
        doc.status = 'cancelado'
        doc.motivo_cancelamento = form.cleaned_data['motivo']
        doc.cancelado_por = request.user
        doc.cancelado_em = timezone.now()
        doc.save(update_fields=['status', 'motivo_cancelamento', 'cancelado_por', 'cancelado_em', 'atualizado_em'])
        sincronizar_aprovacao_pagamento(doc, request.user)
        doc.lancamentos.filter(status__in=('rascunho', 'em_validacao')).update(status='cancelado')
        AprovacaoRegistro.objects.filter(pk__in=aprovacoes_bloqueadas, status='pendente').update(
            status='cancelado',
            comentario=f'Documento cancelado: {form.cleaned_data["motivo"]}',
        )
        messages.success(request, 'Documento cancelado. O arquivo e o histórico foram preservados.')
        return redirect('detalhe_documento', pk=pk)
    return render(request, 'financeiro/cancelar_documento.html', {
        'documento': doc, 'form': form,
    }, status=400 if request.method == 'POST' else 200)


def _aplicar_situacao_pagamento(doc, dados, usuario):
    """Atualiza a baixa sob o bloqueio do documento e a autorização vigente."""
    situacao = dados['situacao_pagamento']
    data = dados['data_pagamento']
    if doc.situacao_pagamento in {'pago', 'recebido'}:
        if situacao != doc.situacao_pagamento or data != doc.data_pagamento:
            raise ValidationError('Pagamento ou recebimento já realizado. Utilize uma correção ou estorno auditável para alterar a baixa.')
        return
    if situacao == 'pago':
        exigir_aprovacao_pagamento(doc)
    doc.situacao_pagamento = situacao
    doc.data_pagamento = data
    doc.save(update_fields=['situacao_pagamento', 'data_pagamento', 'atualizado_em'])
    if situacao != 'pago':
        sincronizar_aprovacao_pagamento(doc, usuario)


@login_required
@access_required(**ACESSO_PAGAMENTO)
@require_POST
@transaction.atomic
def atualizar_pagamento_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=pk)
    if doc.status == 'cancelado':
        messages.error(request, 'Documento cancelado. O pagamento não pode ser alterado.')
        return redirect('detalhe_documento', pk=pk)
    form = PagamentoDocumentoForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                _aplicar_situacao_pagamento(doc, form.cleaned_data, request.user)
        except ValidationError as exc:
            doc.refresh_from_db()
            form.add_error(None, exc)
        else:
            messages.success(request, 'Situação do pagamento atualizada.')
            return redirect('detalhe_documento', pk=pk)
    return render(request, 'financeiro/detalhe_documento.html', {
        'documento': doc, 'lancamentos': doc.lancamentos.all(),
        'pagamento_form': form, 'pode_alterar_pagamento': True,
        'pode_cancelar': doc.pode_cancelar,
        'situacao_aprovacao': situacao_aprovacao_pagamento(doc),
    }, status=400)


@login_required
def detalhe_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro, pk=pk)
    return render(request, 'financeiro/detalhe_documento.html', {
        'documento': doc,
        'lancamentos': doc.lancamentos.all(),
        'pagamento_form': PagamentoDocumentoForm.para_documento(doc),
        'pode_alterar_pagamento': doc.status != 'cancelado' and user_has_access(request.user, **ACESSO_PAGAMENTO),
        'pode_cancelar': user_has_access(request.user, **ACESSO_PAGAMENTO) and doc.pode_cancelar,
        'situacao_aprovacao': situacao_aprovacao_pagamento(doc),
    })


@login_required
@access_required(**ACESSO_PAGAMENTO)
@require_POST
@transaction.atomic
def solicitar_aprovacao_pagamento_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=pk)
    if doc.status == 'cancelado' or doc.situacao_pagamento != 'a_pagar':
        messages.error(request, 'Somente documentos a pagar podem ser enviados para aprovação de pagamento.')
    else:
        try:
            with transaction.atomic():
                sincronizar_aprovacao_pagamento(doc, request.user, reenviar=True)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(request, 'Pagamento encaminhado para aprovação de Luiz.')
    return redirect('detalhe_documento', pk=pk)


@login_required
@access_required(**ACESSO_PAGAMENTO)
@transaction.atomic
def editar_detalhamento_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=pk)
    form = DetalhamentoDocumentoForm(request.POST if request.method == 'POST' else None, instance=doc)
    if request.method == 'POST' and form.is_valid():
        # Apenas metadados: não altera valores, baixas, datas ou o arquivo original.
        try:
            with transaction.atomic():
                form.save()
                if doc.situacao_pagamento != 'pago':
                    sincronizar_aprovacao_pagamento(doc, request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Descrição e observações atualizadas.')
            return redirect('detalhe_documento', pk=pk)
    return render(request, 'financeiro/editar_detalhamento.html', {'form': form, 'documento': doc})


@login_required
@access_required(
    permission='financeiro.add_lancamentoerp',
    groups=('Financeiro_Operador', 'Financeiro_Aprovador'),
)
@transaction.atomic
def lancar_erp(request, doc_pk):
    """Lançamento oficial no ERP Grupo PremiumBR"""
    doc = get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=doc_pk)
    if doc.status == 'cancelado':
        messages.error(request, 'Documento cancelado. Não é possível criar um lançamento.')
        return redirect('detalhe_documento', pk=doc.pk)
    pagamento_form = (PagamentoDocumentoForm(request.POST)
        if request.method == 'POST' and 'situacao_pagamento' in request.POST
        else PagamentoDocumentoForm.para_documento(doc))
    if request.method == 'POST':
        if doc.status != 'aprovado_lancamento' or doc.lancamentos.exclude(status='rejeitado').exists():
            messages.error(request, 'O documento nao esta disponivel para um novo lancamento.')
            return redirect('detalhe_documento', pk=doc.pk)
        if not doc.auditoria_aprovada:
            doc.status = 'em_auditoria'
            doc.save(update_fields=['status', 'atualizado_em'])
            messages.error(request, 'Conclua a aprovação de todos os itens da auditoria antes de lançar o documento.')
            return redirect('detalhe_documento', pk=doc.pk)
        descricao = request.POST.get('descricao', '').strip()
        tipo = request.POST.get('tipo', '')
        competencia = request.POST.get('competencia', '')
        centro_custo = request.POST.get('centro_custo', '').strip() or doc.centro_custo
        tipos_validos = {value for value, _ in LancamentoERP.TIPOS}
        if not descricao or not competencia or not centro_custo or tipo not in tipos_validos:
            messages.error(request, 'Dados do lancamento invalidos ou incompletos.')
            return render(request, 'financeiro/lancar_erp.html', {
                'documento': doc,
                'tipos': LancamentoERP.TIPOS, 'pagamento_form': pagamento_form,
            })
        if pagamento_form.is_bound and not pagamento_form.is_valid():
            return render(request, 'financeiro/lancar_erp.html', {
                'documento': doc, 'tipos': LancamentoERP.TIPOS, 'pagamento_form': pagamento_form,
            })
        lancamento = LancamentoERP(
            documento=doc,
            descricao=descricao,
            tipo=tipo,
            valor=doc.valor,
            centro_custo=centro_custo,
            competencia=competencia,
            status='em_validacao',
            lancado_por=request.user,
        )
        try:
            with transaction.atomic():
                if pagamento_form.is_bound:
                    _aplicar_situacao_pagamento(doc, pagamento_form.cleaned_data, request.user)
                elif doc.situacao_pagamento != 'pago':
                    sincronizar_aprovacao_pagamento(doc, request.user)
                lancamento.full_clean()
                lancamento.save()
                AprovacaoRegistro.criar_para(
                    objeto=lancamento,
                    titulo=f'Lançamento financeiro: {doc.numero_documento}',
                    descricao=f'{descricao} — R$ {lancamento.valor} — {centro_custo}',
                    modulo='financeiro',
                    solicitado_por=request.user,
                )
        except ValidationError as exc:
            doc.refresh_from_db()
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'financeiro/lancar_erp.html', {
                'documento': doc,
                'tipos': LancamentoERP.TIPOS, 'pagamento_form': pagamento_form,
            })
        doc.status = 'lancado'
        doc.save()
        messages.info(request, 'Lançamento contábil encaminhado para aprovação de Thiago. A aprovação do pagamento é separada, com Luiz.')
        return redirect('detalhe_documento', pk=doc.pk)
    return render(request, 'financeiro/lancar_erp.html', {
        'documento': doc,
        'tipos': LancamentoERP.TIPOS, 'pagamento_form': pagamento_form,
    })


@login_required
@access_required(
    permission='financeiro.change_lancamentoerp',
    groups=('Financeiro_Aprovador', 'Diretoria_Final'),
)
@transaction.atomic
def validar_lancamento(request, pk):
    """Compatibilidade: a decisão contábil passa pela fila do responsável operacional."""
    lancamento = get_object_or_404(LancamentoERP.objects.select_related('documento'), pk=pk)
    documento = lancamento.documento
    if documento.status == 'cancelado':
        messages.error(request, 'Documento cancelado. O lançamento não pode ser validado.')
        return redirect('detalhe_documento', pk=documento.pk)
    if request.method == 'POST':
        if lancamento.status != 'em_validacao':
            messages.error(request, 'Este lancamento nao esta aguardando validacao.')
            return redirect('painel_financeiro')
        acao = request.POST.get('acao')
        if acao not in {'validar', 'rejeitar'}:
            messages.error(request, 'Acao de validacao invalida.')
            return redirect('validar_lancamento', pk=pk)
        aprovacao = get_object_or_404(
            AprovacaoRegistro,
            content_type__app_label='financeiro',
            content_type__model='lancamentoerp',
            object_id=lancamento.pk,
            destinatario=request.user,
            status='pendente',
        )
        from core.views_aprovacao import aprovar_registro, rejeitar_registro
        dados = request.POST.copy()
        dados['next'] = reverse('painel_financeiro')
        request.POST = dados
        decisao = aprovar_registro if acao == 'validar' else rejeitar_registro
        return decisao(request, aprovacao.pk)
    return render(request, 'financeiro/validar_lancamento.html', {
        'lancamento': lancamento,
        'pode_aprovar': AprovacaoRegistro.objects.filter(
            content_type__app_label='financeiro', content_type__model='lancamentoerp',
            object_id=lancamento.pk, destinatario=request.user, status='pendente',
        ).exists(),
    })


@login_required
def download_pdf_financeiro(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro, pk=pk)
    
    # 1. Tenta baixar da Nuvem (S3 / Supabase Storage)
    if doc.arquivo:
        return redirect(doc.arquivo.url)
        
    # 2. Fallback: Banco de Dados Legado
    if doc.arquivo_pdf:
        response = HttpResponse(doc.arquivo_pdf, content_type='application/pdf')
        filename = get_valid_filename(f'NF_{doc.numero_documento}.pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
        
    messages.error(request, '❌ Arquivo PDF não encontrado.')
    return redirect('detalhe_documento', pk=pk)
