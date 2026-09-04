"""ERP Grupo PremiumBR — Views do Módulo 5: Compras"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import F
from django.db import transaction
from decimal import Decimal, InvalidOperation
from .models import Material, SolicitacaoMaterial, PedidoCompra
from core.access import access_required
from django.core.exceptions import ValidationError


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
@access_required(permission='compras.add_solicitacaomaterial', profiles=('compras', 'gestor'))
@transaction.atomic
def nova_solicitacao(request):
    if request.method == 'POST':
        material_pk = request.POST.get('material')
        quantidade = request.POST.get('quantidade_solicitada')
        justificativa = request.POST.get('justificativa', '').strip()
        unidade_destino = request.POST.get('unidade_destino', '').strip()

        if not all([material_pk, quantidade, justificativa, unidade_destino]):
            messages.error(request, '⚠️ GATEWAY: Preencha todos os campos obrigatórios.')
            return render(request, 'compras/nova_solicitacao.html', {
                'materiais': Material.objects.all(),
                'post_data': request.POST,
            })

        material = get_object_or_404(Material.objects.select_for_update(), pk=material_pk)
        try:
            qtd = Decimal(quantidade.replace(',', '.'))
        except (InvalidOperation, AttributeError):
            qtd = Decimal('0')
        if qtd <= 0:
            messages.error(request, 'A quantidade deve ser maior que zero.')
            return render(request, 'compras/nova_solicitacao.html', {
                'materiais': Material.objects.all(),
                'post_data': request.POST,
            })

        sol = SolicitacaoMaterial(
            material=material,
            quantidade_solicitada=qtd,
            solicitante=request.user.get_full_name() or request.user.username,
            solicitante_usuario=request.user,
            unidade_destino=unidade_destino,
            justificativa=justificativa,
            status='em_analise',
        )
        try:
            sol.full_clean()
            sol.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'compras/nova_solicitacao.html', {
                'materiais': Material.objects.all(),
                'post_data': request.POST,
            })

        # Gateway de Estoque: material disponível?
        if material.quantidade_estoque >= qtd:
            sol.status = 'atendido_interno'
            material.quantidade_estoque -= qtd
            material.save(update_fields=['quantidade_estoque', 'atualizado_em'])
            sol.save(update_fields=['status', 'atualizado_em'])
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
@access_required(permission='compras.add_pedidocompra', profiles=('compras', 'gestor'))
@transaction.atomic
def criar_pedido_compra(request, solicitacao_pk):
    sol = get_object_or_404(SolicitacaoMaterial.objects.select_for_update(), pk=solicitacao_pk)
    if request.method == 'POST':
        if sol.status != 'compra_externa':
            messages.error(request, 'A solicitacao nao esta disponivel para compra externa.')
            return redirect('detalhe_solicitacao', pk=sol.pk)
        fornecedor = request.POST.get('fornecedor', '').strip()
        if not fornecedor:
            messages.error(request, 'Informe o fornecedor.')
            return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})
        try:
            valor_unit = Decimal(request.POST['valor_unitario'].replace(',', '.'))
        except (InvalidOperation, KeyError):
            valor_unit = Decimal('0')
        if valor_unit <= 0:
            messages.error(request, 'O valor unitario deve ser maior que zero.')
            return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})
        pedido = PedidoCompra(
            solicitacao=sol,
            fornecedor=fornecedor,
            cnpj_fornecedor=request.POST.get('cnpj_fornecedor', ''),
            valor_unitario=valor_unit,
            valor_total=valor_unit * sol.quantidade_solicitada,
            prazo_entrega=request.POST.get('prazo_entrega') or None,
            status='aguardando_aprovacao',
        )
        try:
            pedido.full_clean()
            pedido.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})
        messages.info(request,
            f'📋 Pedido de compra criado. Aguardando aprovação.')
        return redirect('detalhe_solicitacao', pk=solicitacao_pk)
    return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})


@login_required
@access_required(
    permission='compras.change_pedidocompra',
    groups=('Compras_Aprovador', 'Diretoria_Final'),
)
@transaction.atomic
def aprovar_pedido(request, pk):
    """Gateway de Aprovação de Compra"""
    pedido = get_object_or_404(PedidoCompra.objects.select_for_update(), pk=pk)
    if request.method == 'POST':
        if pedido.status != 'aguardando_aprovacao':
            messages.error(request, 'Este pedido nao esta aguardando aprovacao.')
            return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)
        acao = request.POST.get('acao')
        if acao == 'aprovar':
            pedido.status = 'pedido_emitido'
            pedido.aprovado_por = request.user
            pedido.save()
            messages.success(request,
                f'✅ GATEWAY: Compra aprovada! Pedido emitido ao fornecedor {pedido.fornecedor}.')
        elif acao == 'reprovar':
            pedido.status = 'reprovado'
            pedido.obs = request.POST.get('obs', 'Reprovado — nova cotação necessária.')
            pedido.save()
            messages.warning(request,
                f'⚠️ GATEWAY: Compra reprovada. Processo retorna para nova cotação.')
        else:
            messages.error(request, 'Acao de aprovacao invalida.')
            return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)
        return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)
    return render(request, 'compras/aprovar_pedido.html', {'pedido': pedido})
