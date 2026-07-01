"""ERP Grupo Premium — Views do Módulo 5: Compras"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import F
from .models import Material, SolicitacaoMaterial, PedidoCompra


@login_required
def painel_compras(request):
    materiais_criticos = Material.objects.filter(quantidade_estoque__lte=F('estoque_minimo'))
    solicitacoes_pendentes = SolicitacaoMaterial.objects.filter(
        status__in=['pendente', 'em_analise'])
    pedidos_abertos = PedidoCompra.objects.exclude(
        status__in=['concluido'])

    return render(request, 'compras/painel.html', {
        'materiais_criticos': materiais_criticos,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'pedidos_abertos': pedidos_abertos,
        'total_materiais': Material.objects.count(),
        'total_estoque_critico': materiais_criticos.count(),
    })


@login_required
def lista_materiais(request):
    materiais = Material.objects.all()
    busca = request.GET.get('q', '')
    if busca:
        materiais = materiais.filter(nome__icontains=busca)
    return render(request, 'compras/lista_materiais.html', {
        'materiais': materiais,
        'busca': busca,
    })


@login_required
def nova_solicitacao(request):
    if request.method == 'POST':
        material_pk = request.POST.get('material')
        quantidade = request.POST.get('quantidade_solicitada')
        justificativa = request.POST.get('justificativa', '').strip()

        if not all([material_pk, quantidade, justificativa]):
            messages.error(request, '⚠️ GATEWAY: Preencha todos os campos obrigatórios.')
            return render(request, 'compras/nova_solicitacao.html', {
                'materiais': Material.objects.all(),
                'post_data': request.POST,
            })

        material = get_object_or_404(Material, pk=material_pk)
        qtd = float(quantidade)

        sol = SolicitacaoMaterial(
            material=material,
            quantidade_solicitada=qtd,
            solicitante=request.user.get_full_name() or request.user.username,
            solicitante_usuario=request.user,
            unidade_destino=request.POST.get('unidade_destino', ''),
            justificativa=justificativa,
            status='em_analise',
        )
        sol.save()

        # Gateway de Estoque: material disponível?
        if material.quantidade_estoque >= qtd:
            sol.status = 'atendido_interno'
            material.quantidade_estoque -= qtd
            material.save()
            sol.save()
            messages.success(request,
                f'✅ GATEWAY ESTOQUE: Material disponível! {material.nome} x{qtd} separado do estoque '
                f'e encaminhado para entrega. Estoque atualizado: {material.quantidade_estoque} '
                f'{material.get_unidade_medida_display()}.')
        else:
            sol.status = 'compra_externa'
            sol.save()
            messages.warning(request,
                f'⚠️ GATEWAY ESTOQUE: Material "{material.nome}" insuficiente em estoque '
                f'(disponível: {material.quantidade_estoque}). Encaminhado para COMPRA EXTERNA.')

        return redirect('detalhe_solicitacao', pk=sol.pk)

    return render(request, 'compras/nova_solicitacao.html', {
        'materiais': Material.objects.all(),
    })


@login_required
def detalhe_solicitacao(request, pk):
    sol = get_object_or_404(SolicitacaoMaterial, pk=pk)
    return render(request, 'compras/detalhe_solicitacao.html', {
        'solicitacao': sol,
        'pedidos': sol.pedidos.all(),
    })


@login_required
def criar_pedido_compra(request, solicitacao_pk):
    sol = get_object_or_404(SolicitacaoMaterial, pk=solicitacao_pk)
    if request.method == 'POST':
        valor_unit = float(request.POST['valor_unitario'])
        pedido = PedidoCompra(
            solicitacao=sol,
            fornecedor=request.POST['fornecedor'],
            cnpj_fornecedor=request.POST.get('cnpj_fornecedor', ''),
            valor_unitario=valor_unit,
            valor_total=valor_unit * float(sol.quantidade_solicitada),
            prazo_entrega=request.POST.get('prazo_entrega') or None,
            status='aguardando_aprovacao',
        )
        pedido.save()
        messages.info(request,
            f'📋 Pedido de compra criado. Aguardando aprovação.')
        return redirect('detalhe_solicitacao', pk=solicitacao_pk)
    return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})


@login_required
def aprovar_pedido(request, pk):
    """Gateway de Aprovação de Compra"""
    pedido = get_object_or_404(PedidoCompra, pk=pk)
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'aprovar':
            # Validação Final do Luiz para o centro de custo "Compras Almoxarifado"
            unidade = pedido.solicitacao.unidade_destino.lower()
            eh_luiz = request.user.username.lower() == 'luiz' or 'luiz' in request.user.get_full_name().lower()

            if ('almoxarifado' in unidade or 'compras' in unidade) and not eh_luiz:
                messages.error(request, '❌ Apenas o "Luiz" pode aprovar processos de Compras do Almoxarifado.')
                return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)

            pedido.status = 'pedido_emitido'
            pedido.aprovado_por = request.user
            pedido.save()
            messages.success(request,
                f'✅ GATEWAY: Compra aprovada! Pedido emitido ao fornecedor {pedido.fornecedor}.')
        else:
            pedido.status = 'reprovado'
            pedido.obs = request.POST.get('obs', 'Reprovado — nova cotação necessária.')
            pedido.save()
            messages.warning(request,
                f'⚠️ GATEWAY: Compra reprovada. Processo retorna para nova cotação.')
        return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)
    return render(request, 'compras/aprovar_pedido.html', {'pedido': pedido})
