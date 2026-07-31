from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Ativo, RegistroManutencao

@login_required
def painel_manutencao(request):
    ativos = Ativo.objects.all()
    manutencoes_abertas = RegistroManutencao.objects.filter(status__in=['aberta', 'andamento'])
    manutencoes_recentes = RegistroManutencao.objects.all()[:10]

    return render(request, 'manutencao/painel.html', {
        'total_ativos': ativos.count(),
        'ativos_manutencao': ativos.filter(status='manutencao').count(),
        'manutencoes_abertas': manutencoes_abertas.count(),
        'manutencoes_recentes': manutencoes_recentes,
    })

@login_required
def lista_ativos(request):
    ativos = Ativo.objects.all()
    return render(request, 'manutencao/lista_ativos.html', {'ativos': ativos})

@login_required
def novo_ativo(request):
    if request.method == 'POST':
        ativo = Ativo(
            numero_patrimonio=request.POST['numero_patrimonio'],
            nome=request.POST['nome'],
            descricao=request.POST.get('descricao', ''),
            unidade_atual=request.POST['unidade_atual'],
            status=request.POST.get('status', 'ativo'),
        )
        data_aquisicao = request.POST.get('data_aquisicao')
        if data_aquisicao:
            ativo.data_aquisicao = data_aquisicao
        
        valor_aquisicao = request.POST.get('valor_aquisicao')
        if valor_aquisicao:
            ativo.valor_aquisicao = valor_aquisicao.replace(',', '.')

        ativo.save()
        messages.success(request, f'✅ Ativo {ativo.numero_patrimonio} cadastrado com sucesso!')
        return redirect('lista_ativos')
    return render(request, 'manutencao/form_ativo.html')

@login_required
def editar_ativo(request, pk):
    ativo = get_object_or_404(Ativo, pk=pk)
    if request.method == 'POST':
        ativo.numero_patrimonio = request.POST['numero_patrimonio']
        ativo.nome = request.POST['nome']
        ativo.descricao = request.POST.get('descricao', '')
        ativo.unidade_atual = request.POST['unidade_atual']
        ativo.status = request.POST.get('status', 'ativo')
        
        data_aquisicao = request.POST.get('data_aquisicao')
        if data_aquisicao:
            ativo.data_aquisicao = data_aquisicao
            
        valor_aquisicao = request.POST.get('valor_aquisicao')
        if valor_aquisicao:
            ativo.valor_aquisicao = valor_aquisicao.replace(',', '.')

        ativo.save()
        messages.success(request, f'✅ Ativo {ativo.numero_patrimonio} atualizado.')
        return redirect('lista_ativos')
    return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})

@login_required
def lista_manutencoes(request):
    manutencoes = RegistroManutencao.objects.all()
    return render(request, 'manutencao/lista_manutencoes.html', {'manutencoes': manutencoes})

@login_required
def nova_manutencao(request):
    if request.method == 'POST':
        ativo = get_object_or_404(Ativo, pk=request.POST['ativo'])
        
        # Muda o status do ativo
        ativo.status = 'manutencao'
        ativo.save()

        manut = RegistroManutencao(
            ativo=ativo,
            unidade_origem=request.POST['unidade_origem'],
            motivo=request.POST['motivo'],
            data_inicio=request.POST['data_inicio'],
            status='aguardando_aprovacao',
            fornecedor_servico=request.POST.get('fornecedor_servico', ''),
            obs=request.POST.get('obs', ''),
            registrado_por=request.user
        )
        manut.save()
        
        from core.models import AprovacaoRegistro
        from django.contrib.contenttypes.models import ContentType
        AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(manut),
            object_id=manut.id,
            modulo='manutencao',
            nivel=2,
            titulo=f"Manutenção: {ativo.nome} ({manut.unidade_origem})",
            descricao=f"Motivo: {manut.motivo}",
            solicitado_por=request.user
        )
        
        messages.success(request, f'🔧 Solicitação de manutenção aberta para {ativo.nome} e enviada para aprovação do CEO.')
        return redirect('lista_manutencoes')
    
    ativos = Ativo.objects.filter(status='ativo')
    return render(request, 'manutencao/form_manutencao.html', {'ativos': ativos})

@login_required
def concluir_manutencao(request, pk):
    manut = get_object_or_404(RegistroManutencao, pk=pk)
    if request.method == 'POST':
        manut.status = request.POST.get('status', 'concluida')
        manut.data_conclusao = request.POST.get('data_conclusao') or timezone.now().date()
        manut.fornecedor_servico = request.POST.get('fornecedor_servico', '')
        manut.obs = request.POST.get('obs', '')
        
        custo = request.POST.get('custo_reparo')
        if custo:
            manut.custo_reparo = custo.replace(',', '.')
            
        manut.save()

        if manut.status == 'concluida':
            ativo = manut.ativo
            ativo.status = 'ativo'
            ativo.unidade_atual = request.POST.get('unidade_retorno', manut.unidade_origem)
            ativo.save()
            messages.success(request, f'✅ Manutenção concluída. O ativo retornou para uso.')
        else:
            messages.success(request, f'✅ Manutenção atualizada.')
            
        return redirect('lista_manutencoes')
    
    return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})
