"""ERP Grupo PremiumBR — Views do Módulo 2: Admissional"""
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
            doc.arquivo = arquivo_upload.read()
            arquivo_upload.seek(0)
            
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
                    data_inicio_str = request.POST.get('data_inicio')
                    data_inicio_obj = timezone.now().date()
                    if data_inicio_str:
                        from datetime import datetime
                        try:
                            data_inicio_obj = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                        except:
                            pass
                    
                    colab = Colaborador(
                        nome=admissao.candidato_nome,
                        cpf=request.POST.get('cpf', '000.000.000-00'),
                        email=admissao.candidato_email,
                        telefone=admissao.candidato_telefone or '',
                        cargo=admissao.vaga_nome,
                        unidade=admissao.unidade_destino,
                        data_admissao=data_inicio_obj,
                        status='ativo',
                    )
                    colab.save()
                    admissao.colaborador = colab
                    admissao.data_inicio = data_inicio_obj
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


import csv
from django.http import HttpResponse
from datetime import timedelta
from .models import PresencaDiaria

@login_required
def controle_presenca(request):
    from datetime import datetime
    data_str = request.GET.get('data') or request.POST.get('data')
    unidade_filter = request.GET.get('unidade', '')
    
    if data_str:
        try:
            data_selecionada = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data_selecionada = timezone.now().date()
    else:
        data_selecionada = timezone.now().date()
        
    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('colaborador_'):
                colab_pk = key.split('_')[1]
                status = request.POST.get(f'status_{colab_pk}')
                obs = request.POST.get(f'obs_{colab_pk}', '')
                
                PresencaDiaria.objects.update_or_create(
                    colaborador_id=colab_pk,
                    data=data_selecionada,
                    defaults={'status': status, 'observacao': obs}
                )
        messages.success(request, f'Presenças salvas com sucesso para o dia {data_selecionada.strftime("%d/%m/%Y")}!')
        return redirect(f"{request.path}?data={data_selecionada}&unidade={unidade_filter}")

    colaboradores = Colaborador.objects.filter(status='ativo')
    if unidade_filter:
        colaboradores = colaboradores.filter(unidade__icontains=unidade_filter)
        
    presencas = []
    for c in colaboradores:
        try:
            p, _ = PresencaDiaria.objects.get_or_create(colaborador=c, data=data_selecionada)
            p.status_choices = PresencaDiaria.STATUS_CHOICES
            presencas.append(p)
        except Exception:
            # Em caso de erro de integridade ou múltiplos objetos (rara inconsistência no DB)
            p = PresencaDiaria.objects.filter(colaborador=c, data=data_selecionada).first()
            if not p:
                p = PresencaDiaria(colaborador=c, data=data_selecionada)
            p.status_choices = PresencaDiaria.STATUS_CHOICES
            presencas.append(p)
        
    return render(request, 'admissional/controle_presenca.html', {
        'presencas': presencas,
        'data_selecionada': data_selecionada,
        'unidade_filter': unidade_filter,
        'status_choices': PresencaDiaria.STATUS_CHOICES,
    })

@login_required
def exportar_presenca_csv(request):
    data_str = request.GET.get('data')
    unidade_filter = request.GET.get('unidade', '')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="presenca_{data_str}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Data', 'Colaborador', 'CPF/Matricula', 'Cliente/Unidade', 'Cidade/UF', 'Status', 'Observacao'])
    
    presencas = PresencaDiaria.objects.filter(data=data_str)
    if unidade_filter:
        presencas = presencas.filter(colaborador__unidade__icontains=unidade_filter)
        
    for p in presencas:
        writer.writerow([
            p.data.strftime("%d/%m/%Y"),
            p.colaborador.nome,
            p.colaborador.cpf,
            p.colaborador.unidade,
            p.colaborador.cidade if hasattr(p.colaborador, 'cidade') else '',
            p.get_status_display(),
            p.observacao
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
