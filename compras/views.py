"""ERP Grupo PremiumBR — Views do Módulo 5: Compras"""
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import F
from django.db import IntegrityError, transaction
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import Material, PedidoCompra, RequisicaoCompra, SolicitacaoMaterial
from .forms import MaterialForm
from core.access import access_required, user_has_access
from core.direct_uploads import assign_direct_upload
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST


STATUS_COMPRA_REALIZADA = {
    'pedido_emitido', 'aguardando_recebimento', 'recebido_conferencia',
    'entrada_estoque', 'concluido',
}


def _normalizar_cnpj(valor):
    valor = valor.strip()
    if not valor:
        return ''
    digitos = re.sub(r'\D', '', valor)
    if len(digitos) != 14:
        raise ValidationError('Informe um CNPJ com 14 dígitos.')
    return f'{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}'


@login_required
def painel_compras(request):
    materiais_criticos = Material.objects.filter(quantidade_estoque__lte=F('estoque_minimo'))
    solicitacoes_pendentes = SolicitacaoMaterial.objects.filter(
        status__in=['pendente', 'em_analise'])
    pedidos_abertos = PedidoCompra.objects.exclude(
        status__in=['concluido', 'reprovado'])
    requisicoes_recentes = RequisicaoCompra.objects.prefetch_related('itens').all()[:10]

    return render(request, 'compras/painel.html', {
        'materiais_criticos': materiais_criticos,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'pedidos_abertos': pedidos_abertos,
        'requisicoes_recentes': requisicoes_recentes,
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
        'can_manage_materials': user_has_access(
            request.user,
            permission='compras.add_material',
            profiles=('compras', 'gestor', 'estoque_compras'),
        ),
    })


@login_required
@access_required(permission='compras.add_material', profiles=('compras', 'gestor', 'estoque_compras'))
def novo_material(request):
    form = MaterialForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        material = form.save(commit=False)
        try:
            if form.cleaned_data['remover_foto'] and not request.FILES.get('foto') and not request.POST.get('direct_upload_foto'):
                material.foto = None
            assign_direct_upload(material, request, 'foto')
            material.full_clean()
            material.save()
        except (ValidationError, OSError) as exc:
            mensagem = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            form.add_error(None, mensagem or 'Não foi possível salvar a foto.')
            return render(request, 'compras/form_material.html', {'form': form, 'acao': 'Novo'})
        messages.success(request, f'Material {material.codigo} cadastrado automaticamente.')
        return redirect('lista_materiais')
    return render(request, 'compras/form_material.html', {'form': form, 'acao': 'Novo'})


@login_required
@access_required(permission='compras.change_material', profiles=('compras', 'gestor', 'estoque_compras'))
def editar_material(request, pk):
    material = get_object_or_404(Material, pk=pk)
    form = MaterialForm(request.POST or None, request.FILES or None, instance=material)
    if request.method == 'POST' and form.is_valid():
        material = form.save(commit=False)
        try:
            if form.cleaned_data['remover_foto'] and not request.FILES.get('foto') and not request.POST.get('direct_upload_foto'):
                material.foto = None
            assign_direct_upload(material, request, 'foto')
            material.full_clean()
            material.save()
        except (ValidationError, OSError) as exc:
            mensagem = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            form.add_error(None, mensagem or 'Não foi possível salvar a foto.')
            return render(request, 'compras/form_material.html', {
                'form': form, 'acao': 'Editar', 'material': material,
            })
        messages.success(request, f'Material {material.codigo} atualizado.')
        return redirect('lista_materiais')
    return render(request, 'compras/form_material.html', {
        'form': form,
        'acao': 'Editar',
        'material': material,
    })


@login_required
@access_required(permission='compras.add_solicitacaomaterial', profiles=('compras', 'gestor', 'estoque_compras'))
@transaction.atomic
def nova_solicitacao(request):
    def render_form(itens_form=None):
        if itens_form is None:
            itens_form = [{
                'material_id': request.GET.get('material', '').strip(),
                'quantidade': '1',
            }]
        return render(request, 'compras/nova_solicitacao.html', {
            'materiais': Material.objects.all(),
            'post_data': request.POST if request.method == 'POST' else {},
            'itens_form': itens_form,
        })

    if request.method == 'POST':
        materiais_post = request.POST.getlist('material')
        quantidades_post = request.POST.getlist('quantidade_solicitada')
        justificativa = request.POST.get('justificativa', '').strip()
        unidade_destino = request.POST.get('unidade_destino', '').strip()
        total_linhas = max(len(materiais_post), len(quantidades_post))
        itens_form = []
        for indice in range(total_linhas):
            material_id = materiais_post[indice].strip() if indice < len(materiais_post) else ''
            quantidade = quantidades_post[indice].strip() if indice < len(quantidades_post) else ''
            if material_id or quantidade:
                itens_form.append({
                    'material_id': material_id,
                    'quantidade': quantidade,
                })

        if not unidade_destino or not justificativa or not itens_form:
            messages.error(request, 'Preencha a unidade, a justificativa e pelo menos um produto.')
            return render_form(itens_form or [{'material_id': '', 'quantidade': '1'}])
        if len(unidade_destino) > 100:
            messages.error(request, 'A unidade de destino deve ter no máximo 100 caracteres.')
            return render_form(itens_form)
        if len(itens_form) > 30:
            messages.error(request, 'Cada requisição pode conter no máximo 30 produtos.')
            return render_form(itens_form[:30])

        itens_validados = []
        materiais_ids = []
        for numero_linha, item in enumerate(itens_form, start=1):
            if not item['material_id'] or not item['quantidade']:
                messages.error(request, f'Informe o produto e a quantidade no item {numero_linha}.')
                return render_form(itens_form)
            try:
                material_id = int(item['material_id'])
                quantidade = Decimal(item['quantidade'].replace(',', '.'))
                SolicitacaoMaterial._meta.get_field('quantidade_solicitada').clean(
                    quantidade, None
                )
            except (TypeError, ValueError, InvalidOperation, ValidationError):
                messages.error(request, f'Informe uma quantidade válida no item {numero_linha}.')
                return render_form(itens_form)
            if quantidade <= 0:
                messages.error(request, f'A quantidade do item {numero_linha} deve ser maior que zero.')
                return render_form(itens_form)
            if material_id in materiais_ids:
                messages.error(request, 'O mesmo produto não pode ser repetido na requisição.')
                return render_form(itens_form)
            materiais_ids.append(material_id)
            itens_validados.append((material_id, quantidade))

        materiais = {
            material.pk: material
            for material in Material.objects.select_for_update().filter(pk__in=materiais_ids)
        }
        if len(materiais) != len(materiais_ids):
            messages.error(request, 'Um dos produtos selecionados não está mais disponível.')
            return render_form(itens_form)

        requisicao = RequisicaoCompra(
            solicitante=request.user.get_full_name() or request.user.username,
            solicitante_usuario=request.user,
            unidade_destino=unidade_destino,
            justificativa=justificativa,
        )
        try:
            requisicao.full_clean()
            requisicao.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render_form(itens_form)

        for material_id, quantidade in itens_validados:
            material = materiais[material_id]
            solicitacao = SolicitacaoMaterial(
                requisicao=requisicao,
                material=material,
                quantidade_solicitada=quantidade,
                solicitante=requisicao.solicitante,
                solicitante_usuario=request.user,
                unidade_destino=unidade_destino,
                justificativa=justificativa,
                status='pendente',
            )
            solicitacao.full_clean()
            solicitacao.save()

        from core.approval_workflow import criar_fluxo_compras
        descricao = (
            f'Unidade: {requisicao.unidade_destino}\n'
            f'Quantidade de produtos: {len(itens_validados)}\n'
            f'Justificativa: {requisicao.justificativa}'
        )
        try:
            criar_fluxo_compras(
                objeto=requisicao,
                titulo=f'RC {requisicao.numero} — {requisicao.unidade_destino}',
                descricao=descricao,
                solicitado_por=request.user,
            )
        except ValidationError as exc:
            transaction.set_rollback(True)
            messages.error(request, '; '.join(exc.messages))
            return render_form(itens_form)
        messages.success(
            request,
            f'Requisição {requisicao.numero} criada e enviada para aprovação da Adriana.',
        )
        return redirect('detalhe_requisicao', pk=requisicao.pk)

    return render_form()


@login_required
def detalhe_requisicao(request, pk):
    requisicao = get_object_or_404(
        RequisicaoCompra.objects.select_related('solicitante_usuario').prefetch_related(
            'itens__material', 'itens__pedidos'
        ),
        pk=pk,
    )
    itens = list(requisicao.itens.all())
    for item in itens:
        item.tem_pedido_ativo = any(
            pedido.status != 'reprovado' for pedido in item.pedidos.all()
        )
    return render(request, 'compras/detalhe_requisicao.html', {
        'requisicao': requisicao,
        'itens': itens,
        'total_itens': len(itens),
        'total_estoque': sum(item.status == 'atendido_interno' for item in itens),
        'total_compra': sum(item.status == 'compra_externa' for item in itens),
    })


@login_required
def detalhe_solicitacao(request, pk):
    sol = get_object_or_404(SolicitacaoMaterial, pk=pk)
    pedidos = sol.pedidos.all()
    return render(request, 'compras/detalhe_solicitacao.html', {
        'solicitacao': sol,
        'pedidos': pedidos,
        'tem_pedido_ativo': pedidos.exclude(status='reprovado').exists(),
    })


@login_required
@access_required(permission='compras.add_pedidocompra', profiles=('compras', 'gestor', 'estoque_compras'))
@transaction.atomic
def criar_pedido_compra(request, solicitacao_pk):
    sol = get_object_or_404(SolicitacaoMaterial.objects.select_for_update(), pk=solicitacao_pk)
    if request.method == 'POST':
        if sol.status != 'compra_externa':
            messages.error(request, 'A solicitacao nao esta disponivel para compra externa.')
            return redirect('detalhe_solicitacao', pk=sol.pk)
        if sol.pedidos.exclude(status='reprovado').exists():
            messages.error(request, 'Esta solicitação já possui um pedido de compra ativo.')
            return redirect('detalhe_solicitacao', pk=sol.pk)
        fornecedor = request.POST.get('fornecedor', '').strip()
        if not fornecedor:
            messages.error(request, 'Informe o fornecedor.')
            return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})
        try:
            valor_unit = Decimal(request.POST['valor_unitario'].replace(',', '.')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
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
            valor_total=(valor_unit * sol.quantidade_solicitada).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            ),
            prazo_entrega=request.POST.get('prazo_entrega') or None,
            status='aguardando_aprovacao',
        )
        try:
            with transaction.atomic():
                pedido.full_clean()
                pedido.save()
        except (ValidationError, IntegrityError) as exc:
            if isinstance(exc, IntegrityError):
                mensagem = 'Esta solicitação já possui um pedido de compra ativo.'
            else:
                mensagem = '; '.join(exc.messages)
            messages.error(request, mensagem)
            return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})

        # ─── Dispara o fluxo de aprovação central ───────────────────────────
        from core.approval_workflow import criar_fluxo_compras
        try:
            criar_fluxo_compras(
                objeto=pedido,
                titulo=f'Pedido de Compra: {sol.material.nome} — {pedido.fornecedor}',
                descricao=(
                    f'Material: {sol.material.nome}\n'
                    f'Unidade destino: {sol.unidade_destino}\n'
                    f'Quantidade: {sol.quantidade_solicitada} {sol.material.get_unidade_medida_display()}\n'
                    f'Fornecedor: {pedido.fornecedor}\n'
                    f'Valor unitário: R$ {pedido.valor_unitario}\n'
                    f'Valor total: R$ {pedido.valor_total}\n'
                    f'Justificativa: {sol.justificativa}'
                ),
                solicitado_por=request.user,
            )
        except ValidationError as exc:
            transaction.set_rollback(True)
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})
        # ────────────────────────────────────────────────────────────────────

        messages.info(request,
            f'📋 Pedido de compra criado. Aguardando aprovação da Adriana.')
        return redirect('detalhe_solicitacao', pk=solicitacao_pk)
    return render(request, 'compras/criar_pedido.html', {'solicitacao': sol})


@login_required
@access_required(
    permission='compras.change_pedidocompra',
    profiles=('compras', 'gestor', 'estoque_compras'),
    groups=('Compras_Aprovador', 'Diretoria_Final'),
)
@transaction.atomic
def aprovar_pedido(request, pk):
    """Compatibilidade: toda decisão passa pela fila nominal central."""
    pedido = get_object_or_404(PedidoCompra.objects.select_for_update(), pk=pk)
    if request.method == 'POST':
        if pedido.status != 'aguardando_aprovacao':
            messages.error(request, 'Este pedido nao esta aguardando aprovacao.')
            return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)
        from core.models import AprovacaoRegistro
        aprovacao = AprovacaoRegistro.objects.filter(
            content_type__app_label='compras',
            content_type__model='pedidocompra',
            object_id=pedido.pk,
            destinatario=request.user,
            status='pendente',
        ).first()
        if not aprovacao:
            messages.error(request, 'Este pedido não está atribuído a você para aprovação.')
            return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)
        acao = request.POST.get('acao')
        if acao == 'aprovar':
            from core.views_aprovacao import aprovar_registro
            return aprovar_registro(request, aprovacao.pk)
        elif acao == 'reprovar':
            motivo = request.POST.get('obs', '').strip() or 'Reprovado — nova cotação necessária.'
            dados = request.POST.copy()
            dados['motivo_rejeicao'] = motivo
            request.POST = dados
            from core.views_aprovacao import rejeitar_registro
            return rejeitar_registro(request, aprovacao.pk)
        else:
            messages.error(request, 'Acao de aprovacao invalida.')
            return redirect('detalhe_solicitacao', pk=pedido.solicitacao.pk)
    return render(request, 'compras/aprovar_pedido.html', {'pedido': pedido})


@login_required
@require_POST
@access_required(
    permission='compras.change_pedidocompra',
    profiles=('compras', 'gestor', 'estoque_compras'),
    groups=('Compras_Aprovador', 'Diretoria_Final'),
)
@transaction.atomic
def atualizar_cnpj_pedido(request, pk):
    pedido = get_object_or_404(PedidoCompra.objects.select_for_update(), pk=pk)
    if pedido.status not in STATUS_COMPRA_REALIZADA:
        messages.error(request, 'O CNPJ poderá ser informado depois que a compra for aprovada e emitida.')
        return redirect('detalhe_solicitacao', pk=pedido.solicitacao_id)

    try:
        cnpj = _normalizar_cnpj(request.POST.get('cnpj_fornecedor', ''))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        pedido.cnpj_fornecedor = cnpj
        pedido.save(update_fields=['cnpj_fornecedor', 'atualizado_em'])
        if cnpj:
            messages.success(request, 'CNPJ do fornecedor atualizado com sucesso.')
        else:
            messages.success(request, 'CNPJ removido. Ele continua sendo um dado opcional.')
    return redirect('detalhe_solicitacao', pk=pedido.solicitacao_id)
