"""ERP Grupo PremiumBR — Views do Módulo 6: Financeiro / Fiscal"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from django.db import transaction
import logging
import json
from decimal import Decimal, InvalidOperation
from .models import DocumentoFinanceiro, AuditoriaItem, LancamentoERP, OrcamentoCentroCusto, ItemDocumentoFinanceiro
from django.http import HttpResponse
from django.core.files.storage import default_storage
from core.access import access_required
from core.validators import validate_document_upload
from core.direct_uploads import verify_direct_upload
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename


logger = logging.getLogger(__name__)


@login_required
def painel_financeiro(request):
    docs_pendentes = DocumentoFinanceiro.objects.filter(status__in=['recebido', 'em_auditoria'])
    lancamentos_pendentes = LancamentoERP.objects.filter(status__in=['rascunho', 'em_validacao'])
    finalizados_mes = LancamentoERP.objects.filter(
        status='finalizado',
        finalizado_em__month=timezone.now().month,
        finalizado_em__year=timezone.now().year,
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
        'docs_pendentes': docs_pendentes,
        'lancamentos_pendentes': lancamentos_pendentes,
        'finalizados_mes': finalizados_mes,
        'total_valor_pendente': sum(d.valor for d in docs_pendentes),
        'total_lancado_mes': sum(l.valor for l in finalizados_mes),
        'dashboard_budget': dashboard_budget,
    })


@login_required
@access_required(permission='financeiro.add_documentofinanceiro', profiles=('financeiro', 'gestor'))
@transaction.atomic
def entrada_documento(request):
    if request.method == 'POST':
        campos_obrigatorios = (
            'tipo', 'numero_documento', 'descricao', 'valor', 'centro_custo',
            'unidade', 'cnpj_emitente', 'razao_social_emitente', 'data_emissao',
        )
        if any(not request.POST.get(campo, '').strip() for campo in campos_obrigatorios):
            messages.error(request, 'Preencha todos os campos obrigatorios.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS,
            })
        try:
            valor_documento = Decimal(request.POST['valor'].replace(',', '.'))
        except (InvalidOperation, ValueError):
            valor_documento = Decimal('-1')
        if valor_documento <= 0:
            messages.error(request, 'O valor do documento deve ser maior que zero.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS,
            })

        doc = DocumentoFinanceiro(
            tipo=request.POST['tipo'],
            numero_documento=request.POST['numero_documento'],
            descricao=request.POST['descricao'],
            valor=valor_documento,
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
        try:
            direct_key = verify_direct_upload(request, 'arquivo_pdf')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS,
            })
        if arquivo_upload:
            try:
                validate_document_upload(arquivo_upload)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'financeiro/entrada_documento.html', {
                    'tipos': DocumentoFinanceiro.TIPOS,
                })
            doc.arquivo = arquivo_upload
        elif direct_key:
            doc.arquivo.name = direct_key
        else:
            messages.error(request, 'Envie o documento em PDF ou imagem valida.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS,
            })

        try:
            doc.full_clean()
            doc.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS,
            })
        except OSError:
            transaction.set_rollback(True)
            messages.error(request, 'Nao foi possivel armazenar o documento. Tente novamente.')
            return render(request, 'financeiro/entrada_documento.html', {
                'tipos': DocumentoFinanceiro.TIPOS,
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
                'tipos': DocumentoFinanceiro.TIPOS,
            })

        # Criar checklist de auditoria automaticamente
        for item_key, _ in AuditoriaItem.ITENS_CHECKLIST:
            AuditoriaItem.objects.create(documento=doc, item=item_key, status='pendente')

        messages.info(request,
            f'📋 Documento {doc.numero_documento} recebido. Iniciando auditoria interna...')
        return redirect('auditoria_documento', pk=doc.pk)

    return render(request, 'financeiro/entrada_documento.html', {
        'tipos': DocumentoFinanceiro.TIPOS,
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
@access_required(
    permission='financeiro.add_lancamentoerp',
    groups=('Financeiro_Operador', 'Financeiro_Aprovador'),
)
@transaction.atomic
def lancar_erp(request, doc_pk):
    """Lançamento oficial no ERP Grupo PremiumBR"""
    doc = get_object_or_404(DocumentoFinanceiro.objects.select_for_update(), pk=doc_pk)
    if request.method == 'POST':
        if doc.status != 'aprovado_lancamento' or doc.lancamentos.exclude(status='rejeitado').exists():
            messages.error(request, 'O documento nao esta disponivel para um novo lancamento.')
            return redirect('detalhe_documento', pk=doc.pk)
        descricao = request.POST.get('descricao', '').strip()
        tipo = request.POST.get('tipo', '')
        competencia = request.POST.get('competencia', '')
        tipos_validos = {value for value, _ in LancamentoERP.TIPOS}
        if not descricao or not competencia or tipo not in tipos_validos:
            messages.error(request, 'Dados do lancamento invalidos ou incompletos.')
            return render(request, 'financeiro/lancar_erp.html', {
                'documento': doc,
                'tipos': LancamentoERP.TIPOS,
            })
        lancamento = LancamentoERP(
            documento=doc,
            descricao=descricao,
            tipo=tipo,
            valor=doc.valor,
            centro_custo=doc.centro_custo,
            competencia=competencia,
            status='em_validacao',
            lancado_por=request.user,
        )
        try:
            lancamento.full_clean()
            lancamento.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'financeiro/lancar_erp.html', {
                'documento': doc,
                'tipos': LancamentoERP.TIPOS,
            })
        doc.status = 'lancado'
        doc.save()
        messages.info(request, f'📊 Lançamento criado. Aguardando validação final.')
        return redirect('validar_lancamento', pk=lancamento.pk)
    return render(request, 'financeiro/lancar_erp.html', {
        'documento': doc,
        'tipos': LancamentoERP.TIPOS,
    })


@login_required
@access_required(
    permission='financeiro.change_lancamentoerp',
    groups=('Financeiro_Aprovador', 'Diretoria_Final'),
)
@transaction.atomic
def validar_lancamento(request, pk):
    """Gateway 2: Lançamento validado → FINALIZADO NO ERP GRUPO PREMIUMBR"""
    lancamento = get_object_or_404(LancamentoERP.objects.select_for_update(), pk=pk)
    documento = DocumentoFinanceiro.objects.select_for_update().get(pk=lancamento.documento_id)
    if request.method == 'POST':
        if lancamento.status != 'em_validacao':
            messages.error(request, 'Este lancamento nao esta aguardando validacao.')
            return redirect('painel_financeiro')
        acao = request.POST.get('acao')
        if acao == 'validar':
            lancamento.status = 'finalizado'
            lancamento.validado_por = request.user
            lancamento.finalizado_em = timezone.now()
            lancamento.save()
            documento.status = 'arquivado'
            documento.save(update_fields=['status', 'atualizado_em'])
            messages.success(request,
                '🏆 GATEWAY FINAL: Lançamento VALIDADO e FINALIZADO NO ERP GRUPO PREMIUMBR! '
                'Documento arquivado digitalmente. Prestação de contas concluída.')
        elif acao == 'rejeitar':
            motivo = request.POST.get('motivo_rejeicao', '').strip()
            if not motivo:
                messages.error(request, 'Informe o motivo da rejeicao.')
                return redirect('validar_lancamento', pk=pk)
            lancamento.status = 'rejeitado'
            lancamento.motivo_rejeicao = motivo
            lancamento.save()
            documento.status = 'aprovado_lancamento'
            documento.save(update_fields=['status', 'atualizado_em'])
            messages.error(request,
                '❌ GATEWAY: Lançamento rejeitado. Registro reaberto para correção.')
        else:
            messages.error(request, 'Acao de validacao invalida.')
            return redirect('validar_lancamento', pk=pk)
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
        filename = get_valid_filename(f'NF_{doc.numero_documento}.pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
        
    messages.error(request, '❌ Arquivo PDF não encontrado.')
    return redirect('detalhe_documento', pk=pk)
