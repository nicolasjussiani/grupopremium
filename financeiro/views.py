"""ERP Grupo Premium — Views do Módulo 6: Financeiro / Fiscal"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from .models import DocumentoFinanceiro, AuditoriaItem, LancamentoERP, OrcamentoCentroCusto
from django.http import HttpResponse


@login_required
def painel_financeiro(request):
    docs_pendentes = DocumentoFinanceiro.objects.filter(status__in=['recebido', 'em_auditoria'])
    lancamentos_pendentes = LancamentoERP.objects.filter(status__in=['rascunho', 'em_validacao'])
    finalizados_mes = LancamentoERP.objects.filter(
        status='finalizado',
        finalizado_em__month=timezone.now().month
    )
    # Calcula Orcamento/Budget do Mês
    mes_atual = timezone.now().date().replace(day=1)
    
    dashboard_budget = []
    try:
        orcamentos = OrcamentoCentroCusto.objects.filter(competencia=mes_atual)
        for orcamento in orcamentos:
            # Gasto real: Lançamentos finalizados desse centro de custo no mês
            gasto = LancamentoERP.objects.filter(
                centro_custo=orcamento.centro_custo,
                status='finalizado',
                finalizado_em__month=timezone.now().month
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
    except Exception as e:
        # Se a tabela não existir, tenta migrar automaticamente
        from django.core.management import call_command
        try:
            call_command('migrate', interactive=False)
            messages.info(request, "🔄 Banco de dados atualizado automaticamente. Atualize a página.")
        except Exception as mig_e:
            messages.error(request, f"⚠️ Erro ao carregar orçamentos (tabela ausente): {e}")

    return render(request, 'financeiro/painel.html', {
        'docs_pendentes': docs_pendentes,
        'lancamentos_pendentes': lancamentos_pendentes,
        'finalizados_mes': finalizados_mes,
        'total_valor_pendente': sum(d.valor for d in docs_pendentes),
        'total_lancado_mes': sum(l.valor for l in finalizados_mes),
        'dashboard_budget': dashboard_budget,
    })


@login_required
def entrada_documento(request):
    if request.method == 'POST':
        doc = DocumentoFinanceiro(
            tipo=request.POST['tipo'],
            numero_documento=request.POST['numero_documento'],
            descricao=request.POST['descricao'],
            valor=request.POST['valor'],
            centro_custo=request.POST['centro_custo'],
            unidade=request.POST['unidade'],
            cnpj_emitente=request.POST.get('cnpj_emitente', ''),
            razao_social_emitente=request.POST.get('razao_social_emitente', ''),
            contratos_vinculados=request.POST.get('contratos_vinculados', ''),
            data_emissao=request.POST['data_emissao'],
            data_vencimento=request.POST.get('data_vencimento') or None,
            status='em_auditoria',
            recebido_por=request.user,
        )
        
        arquivo_upload = request.FILES.get('arquivo_pdf')
        if arquivo_upload:
            doc.arquivo = arquivo_upload

        doc.save()

        # Criar checklist de auditoria automaticamente
        for item_key, _ in AuditoriaItem.ITENS_CHECKLIST:
            AuditoriaItem.objects.create(documento=doc, item=item_key, status='pendente')

        messages.info(request,
            f'📋 Documento {doc.numero_documento} recebido. Iniciando auditoria interna...')
        return redirect('auditoria_documento', pk=doc.pk)

    return render(request, 'financeiro/entrada_documento.html', {
        'tipos': DocumentoFinanceiro.TIPOS,
    })


@login_required
def auditoria_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro, pk=pk)
    itens = doc.auditoria.all()

    if request.method == 'POST':
        # Atualizar cada item da auditoria
        for item in itens:
            novo_status = request.POST.get(f'item_{item.pk}', 'pendente')
            obs = request.POST.get(f'obs_{item.pk}', '')
            item.status = novo_status
            item.observacao = obs
            item.verificado_por = request.user
            item.save()

        # Gateway 1: Todos os itens OK?
        todos_ok = all(i.status == 'ok' for i in itens)
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
            messages.warning(request, '⚠️ Auditoria parcialmente concluída. Verifique todos os itens.')

        return redirect('detalhe_documento', pk=pk)

    return render(request, 'financeiro/auditoria.html', {
        'documento': doc,
        'itens': itens,
        'status_choices': AuditoriaItem.STATUS,
    })


@login_required
def detalhe_documento(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro, pk=pk)
    return render(request, 'financeiro/detalhe_documento.html', {
        'documento': doc,
        'lancamentos': doc.lancamentos.all(),
    })


@login_required
def lancar_erp(request, doc_pk):
    """Lançamento oficial no ERP Grupo Premium"""
    doc = get_object_or_404(DocumentoFinanceiro, pk=doc_pk)
    if request.method == 'POST':
        lancamento = LancamentoERP(
            documento=doc,
            descricao=request.POST['descricao'],
            tipo=request.POST['tipo'],
            valor=doc.valor,
            centro_custo=doc.centro_custo,
            competencia=request.POST['competencia'],
            status='em_validacao',
            lancado_por=request.user,
        )
        lancamento.save()
        doc.status = 'lancado'
        doc.save()
        messages.info(request, f'📊 Lançamento criado. Aguardando validação final.')
        return redirect('validar_lancamento', pk=lancamento.pk)
    return render(request, 'financeiro/lancar_erp.html', {
        'documento': doc,
        'tipos': LancamentoERP.TIPOS,
    })


@login_required
def validar_lancamento(request, pk):
    """Gateway 2: Lançamento validado → FINALIZADO NO ERP GRUPO PREMIUM"""
    lancamento = get_object_or_404(LancamentoERP, pk=pk)
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'validar':
            # Validação Final do Luiz para o centro de custo "Financeiro Compras RH"
            # O último a aprovar as cargas e processos é o Luiz
            centro = lancamento.centro_custo.lower()
            eh_luiz = request.user.username.lower() == 'luiz' or 'luiz' in request.user.get_full_name().lower()

            if ('compras' in centro or 'rh' in centro or 'financeiro' in centro) and not eh_luiz:
                messages.error(request, '❌ Apenas o "Luiz" pode aprovar e finalizar processos do Financeiro Compras RH.')
                return redirect('validar_lancamento', pk=pk)

            lancamento.status = 'finalizado'
            lancamento.validado_por = request.user
            lancamento.finalizado_em = timezone.now()
            lancamento.save()
            lancamento.documento.status = 'arquivado'
            lancamento.documento.save()
            messages.success(request,
                '🏆 GATEWAY FINAL: Lançamento VALIDADO e FINALIZADO NO ERP GRUPO PREMIUM! '
                'Documento arquivado digitalmente. Prestação de contas concluída.')
        else:
            motivo = request.POST.get('motivo_rejeicao', '')
            lancamento.status = 'rejeitado'
            lancamento.motivo_rejeicao = motivo
            lancamento.save()
            messages.error(request,
                '❌ GATEWAY: Lançamento rejeitado. Registro reaberto para correção.')
        return redirect('painel_financeiro')
    return render(request, 'financeiro/validar_lancamento.html', {'lancamento': lancamento})


@login_required
def download_pdf_financeiro(request, pk):
    doc = get_object_or_404(DocumentoFinanceiro, pk=pk)
    
    # 1. Tenta baixar da Nuvem (S3 / Supabase Storage)
    if doc.arquivo:
        return redirect(doc.arquivo.url)
        
    # 2. Fallback: Banco de Dados Legado
    if doc.arquivo_pdf:
        response = HttpResponse(doc.arquivo_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="NF_{doc.numero_documento}.pdf"'
        return response
        
    messages.error(request, '❌ Arquivo PDF não encontrado.')
    return redirect('detalhe_documento', pk=pk)
