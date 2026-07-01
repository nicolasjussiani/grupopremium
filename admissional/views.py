"""ERP Grupo Premium — Views do Módulo 2: Admissional"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Admissao, Colaborador, DocumentoAdmissional
from .forms import ColaboradorForm
from core.models import Notificacao
from sesmet.models import IntegracaoSeguranca, RegistroEPI, OrdemServico
from django.contrib.auth.models import User


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
def atualizar_documento(request, admissao_pk, doc_pk):
    """Gateway de documentação: SIM (aprovado) ou NÃO (pendente/rejeitado)"""
    admissao = get_object_or_404(Admissao, pk=admissao_pk)
    doc = get_object_or_404(DocumentoAdmissional, pk=doc_pk, admissao=admissao)
    if request.method == 'POST':
        novo_status = request.POST.get('status')
        obs = request.POST.get('observacao', '')
        
        arquivo_upload = request.FILES.get('arquivo')
        if arquivo_upload:
            doc.arquivo_nuvem = arquivo_upload
            doc.arquivo_nome = arquivo_upload.name
            doc.arquivo_mimetype = arquivo_upload.content_type
            
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
def avancar_admissao(request, pk):
    """Avança o status do processo admissional"""
    admissao = get_object_or_404(Admissao, pk=pk)
    if request.method == 'POST':
        novo_status = request.POST.get('novo_status')
        obs = request.POST.get('observacoes', '')
        if obs:
            admissao.observacoes = obs

        fluxo_status = [
            'aguardando_documentos', 'documentos_em_analise', 'cadastro_sistema',
            'contrato_gerado', 'integracao', 'epis_entregues', 'liberado', 'concluido'
        ]

        if novo_status in [s[0] for s in Admissao.STATUS]:
            admissao.status = novo_status
            if novo_status == 'concluido':
                admissao.concluido_em = timezone.now()
                # Criar colaborador se ainda não existe
                if not admissao.colaborador:
                    colab = Colaborador(
                        nome=admissao.candidato_nome,
                        cpf=request.POST.get('cpf', '000.000.000-00'),
                        email=admissao.candidato_email,
                        telefone=admissao.candidato_telefone or '',
                        cargo=admissao.vaga_nome,
                        unidade=admissao.unidade_destino,
                        data_admissao=timezone.now().date(),
                        status='ativo',
                    )
                    colab.save()
                    admissao.colaborador = colab
                messages.success(request,
                    f'🎉 Processo admissional de {admissao.candidato_nome} CONCLUÍDO! '
                    f'Colaborador liberado para a unidade.')
            else:
                messages.success(request,
                    f'✅ Status atualizado para: {admissao.get_status_display()}')
            admissao.save()

        return redirect('detalhe_admissao', pk=pk)


@login_required
def lista_colaboradores(request):
    colaboradores = Colaborador.objects.filter(status='ativo')
    return render(request, 'admissional/lista_colaboradores.html', {
        'colaboradores': colaboradores,
        'total': colaboradores.count(),
    })

@login_required
def novo_colaborador(request):
    if request.method == 'POST':
        form = ColaboradorForm(request.POST)
        if form.is_valid():
            colaborador = form.save()
            messages.success(request, f'Colaborador {colaborador.nome} cadastrado com sucesso!')
            return redirect('lista_colaboradores')
    else:
        form = ColaboradorForm()
    return render(request, 'admissional/form_colaborador.html', {'form': form, 'acao': 'Novo'})

@login_required
def editar_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    if request.method == 'POST':
        form = ColaboradorForm(request.POST, instance=colaborador)
        if form.is_valid():
            form.save()
            messages.success(request, f'Colaborador {colaborador.nome} atualizado com sucesso!')
            return redirect('lista_colaboradores')
    else:
        form = ColaboradorForm(instance=colaborador)
    return render(request, 'admissional/form_colaborador.html', {'form': form, 'acao': 'Editar'})

@login_required
def excluir_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    if request.method == 'POST':
        nome = colaborador.nome
        colaborador.delete()
        messages.success(request, f'Colaborador {nome} excluído com sucesso!')
        return redirect('lista_colaboradores')
    return render(request, 'admissional/excluir_colaborador.html', {'colaborador': colaborador})


@login_required
def baixar_documento(request, admissao_pk, doc_pk):
    from django.http import HttpResponse, HttpResponseNotFound
    
    admissao = get_object_or_404(Admissao, pk=admissao_pk)
    doc = get_object_or_404(DocumentoAdmissional, pk=doc_pk, admissao=admissao)
    
    if doc.arquivo_nuvem:
        return redirect(doc.arquivo_nuvem.url)
        
    if doc.arquivo:
        content_type = doc.arquivo_mimetype or 'application/octet-stream'
        filename = doc.arquivo_nome or f'documento_{doc.get_tipo_display()}.bin'
        
        response = HttpResponse(doc.arquivo, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    return HttpResponseNotFound("Arquivo não encontrado.")
