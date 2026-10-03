"""ERP Grupo PremiumBR — Views do Módulo 5: Compras"""
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import F
from django.db import IntegrityError, transaction
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import (
    EquipamentoManutencao, Material, PedidoCompra, RequisicaoCompra,
    SolicitacaoManutencao, SolicitacaoMaterial,
)
from .forms import EquipamentoManutencaoForm, MaterialForm
from core.access import access_required, user_has_access
from core.direct_uploads import assign_direct_upload
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from django.utils import timezone


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
    materiais_produtos = Material.objects.exclude(categoria__in=('manutencao', 'ferramentas'))
    materiais_criticos = materiais_produtos.filter(quantidade_estoque__lte=F('estoque_minimo'))
    solicitacoes_pendentes = SolicitacaoMaterial.objects.filter(
        status__in=['pendente', 'em_analise'])
    pedidos_abertos = PedidoCompra.objects.exclude(
        status__in=['concluido', 'reprovado'])
    pedidos = PedidoCompra.objects.exclude(status='reprovado').select_related(
        'solicitacao__material', 'solicitacao__requisicao',
    ).prefetch_related('solicitacao__pedidos')
    requisicoes_recentes = RequisicaoCompra.objects.prefetch_related('itens').all()

    return render(request, 'compras/painel.html', {
        'materiais_criticos': materiais_criticos,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'pedidos_abertos': pedidos_abertos,
        'pedidos': pedidos,
        'pode_confirmar_entrega': _pode_confirmar_entrega(request.user),
        'requisicoes_recentes': requisicoes_recentes,
        'total_materiais': materiais_produtos.count(),
        'total_estoque_critico': materiais_criticos.count(),
        'total_equipamentos_manutencao': EquipamentoManutencao.objects.filter(ativo=True).count(),
    })


@login_required
def lista_equipamentos_manutencao(request):
    equipamentos = EquipamentoManutencao.objects.all()
    return render(request, 'compras/equipamentos_manutencao.html', {
        'equipamentos': equipamentos,
        'pode_gerenciar': user_has_access(
            request.user,
            permission='compras.add_equipamentomanutencao',
            profiles=('compras', 'gestor', 'estoque_compras'),
        ),
    })


@login_required
@access_required(permission='compras.add_equipamentomanutencao', profiles=('compras', 'gestor', 'estoque_compras'))
def novo_equipamento_manutencao(request):
    form = EquipamentoManutencaoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Equipamento incluído na lista de manutenção.')
        return redirect('lista_equipamentos_manutencao')
    return render(request, 'compras/form_equipamento_manutencao.html', {
        'form': form, 'titulo': 'Novo equipamento',
    })


@login_required
@access_required(permission='compras.change_equipamentomanutencao', profiles=('compras', 'gestor', 'estoque_compras'))
def editar_equipamento_manutencao(request, pk):
    equipamento = get_object_or_404(EquipamentoManutencao, pk=pk)
    form = EquipamentoManutencaoForm(request.POST or None, instance=equipamento)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Equipamento atualizado.')
        return redirect('lista_equipamentos_manutencao')
    return render(request, 'compras/form_equipamento_manutencao.html', {
        'form': form, 'titulo': 'Editar equipamento', 'equipamento': equipamento,
    })


def _pode_confirmar_entrega(usuario):
    return user_has_access(
        usuario, permission='compras.change_solicitacaomaterial',
        profiles=('compras', 'gestor', 'estoque_compras'),
    )


@login_required
def lista_materiais(request):
    materiais = Material.objects.exclude(categoria__in=('manutencao', 'ferramentas'))
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
    def render_form(itens_form=None, manutencoes_form=None):
        if itens_form is None:
            itens_form = [{
                'material_id': request.GET.get('material', '').strip(),
                'quantidade': '1',
                'valor': '',
            }]
        if manutencoes_form is None:
            manutencoes_form = []
        return render(request, 'compras/nova_solicitacao.html', {
            'materiais': Material.objects.exclude(categoria__in=('manutencao', 'ferramentas')),
            'equipamentos': EquipamentoManutencao.objects.filter(ativo=True),
            'post_data': request.POST if request.method == 'POST' else {},
            'itens_form': itens_form,
            'manutencoes_form': manutencoes_form,
        })

    if request.method == 'POST':
        materiais_post = request.POST.getlist('material')
        quantidades_post = request.POST.getlist('quantidade_solicitada')
        valores_post = request.POST.getlist('valor_unitario')
        justificativa = request.POST.get('justificativa', '').strip()
        unidade_destino = request.POST.get('unidade_destino', '').strip()
        equipamentos_post = request.POST.getlist('manutencao_equipamento')
        problemas_post = request.POST.getlist('manutencao_problema')
        manutencoes_form = []
        for indice in range(max(len(equipamentos_post), len(problemas_post))):
            equipamento_id = equipamentos_post[indice].strip() if indice < len(equipamentos_post) else ''
            problema = problemas_post[indice].strip() if indice < len(problemas_post) else ''
            if equipamento_id or problema:
                manutencoes_form.append({
                    'equipamento_id': equipamento_id,
                    'problema': problema,
                })
        total_linhas = max(len(materiais_post), len(quantidades_post))
        itens_form = []
        for indice in range(total_linhas):
            material_id = materiais_post[indice].strip() if indice < len(materiais_post) else ''
            quantidade = quantidades_post[indice].strip() if indice < len(quantidades_post) else ''
            valor = valores_post[indice].strip() if indice < len(valores_post) else ''
            if material_id or valor or (quantidade and quantidade != '1'):
                itens_form.append({
                    'material_id': material_id,
                    'quantidade': quantidade,
                    'valor': valor,
                })

        if not unidade_destino or not justificativa or not (itens_form or manutencoes_form):
            messages.error(request, 'Preencha a unidade, a justificativa e pelo menos um produto ou manutenção.')
            return render_form(itens_form or [{
                'material_id': '', 'quantidade': '1', 'valor': '',
            }], manutencoes_form)
        if len(unidade_destino) > 100:
            messages.error(request, 'A unidade de destino deve ter no máximo 100 caracteres.')
            return render_form(itens_form, manutencoes_form)
        if len(itens_form) > 30:
            messages.error(request, 'Cada requisição pode conter no máximo 30 produtos.')
            return render_form(itens_form[:30], manutencoes_form)
        if len(manutencoes_form) > 30:
            messages.error(request, 'Cada requisição pode conter no máximo 30 solicitações de manutenção.')
            return render_form(itens_form, manutencoes_form[:30])

        itens_validados = []
        materiais_ids = []
        for numero_linha, item in enumerate(itens_form, start=1):
            if not item['material_id'] or not item['quantidade']:
                messages.error(request, f'Informe o produto e a quantidade no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            try:
                material_id = int(item['material_id'])
                quantidade = Decimal(item['quantidade'].replace(',', '.'))
                SolicitacaoMaterial._meta.get_field('quantidade_solicitada').clean(
                    quantidade, None
                )
            except (TypeError, ValueError, InvalidOperation, ValidationError):
                messages.error(request, f'Informe uma quantidade válida no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            if quantidade <= 0:
                messages.error(request, f'A quantidade do item {numero_linha} deve ser maior que zero.')
                return render_form(itens_form, manutencoes_form)
            if material_id in materiais_ids:
                messages.error(request, 'O mesmo produto não pode ser repetido na requisição.')
                return render_form(itens_form, manutencoes_form)
            
            valor_dec = None
            if item.get('valor'):
                try:
                    v_str = item['valor'].replace('R$', '').replace('.', '').replace(',', '.').strip()
                    valor_dec = Decimal(v_str)
                    if valor_dec < 0:
                        raise ValueError
                except:
                    messages.error(request, f'Informe um valor unitário válido no item {numero_linha}.')
                    return render_form(itens_form, manutencoes_form)

            materiais_ids.append(material_id)
            itens_validados.append((material_id, quantidade, valor_dec))

        materiais = {
            material.pk: material
            for material in Material.objects.select_for_update().exclude(
                categoria__in=('manutencao', 'ferramentas')
            ).filter(pk__in=materiais_ids)
        }
        if len(materiais) != len(materiais_ids):
            messages.error(request, 'Um dos produtos selecionados não está mais disponível.')
            return render_form(itens_form, manutencoes_form)

        manutencoes_validadas = []
        for numero_linha, item in enumerate(manutencoes_form, start=1):
            if not item['equipamento_id'] or not item['problema']:
                messages.error(request, f'Informe o equipamento e a manutenção necessária no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            try:
                equipamento_id = int(item['equipamento_id'])
            except (TypeError, ValueError):
                equipamento_id = None
            if equipamento_id is None:
                messages.error(request, f'Selecione um equipamento válido no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            manutencoes_validadas.append((equipamento_id, item['problema']))

        equipamentos = {
            equipamento.pk: equipamento
            for equipamento in EquipamentoManutencao.objects.select_for_update().filter(
                pk__in=[item[0] for item in manutencoes_validadas], ativo=True
            )
        }
        if len(equipamentos) != len(manutencoes_validadas):
            messages.error(request, 'Um dos equipamentos não está mais disponível para solicitação.')
            return render_form(itens_form, manutencoes_form)

        requisicao = RequisicaoCompra(
            solicitante=request.user.get_full_name() or request.user.username,
            solicitante_usuario=request.user,
            unidade_destino=unidade_destino,
            justificativa=justificativa,
        )
        from core.direct_uploads import assign_direct_upload

        try:
            if 'documento' in request.FILES:
                requisicao.documento = request.FILES['documento']
            else:
                assign_direct_upload(requisicao, request, 'documento')

            if 'comprovante_pagamento' in request.FILES:
                requisicao.comprovante_pagamento = request.FILES['comprovante_pagamento']
            else:
                assign_direct_upload(requisicao, request, 'comprovante_pagamento')

            if requisicao.comprovante_pagamento:
                requisicao.status = 'aprovada'
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))
            return render_form(itens_form, manutencoes_form)

        try:
            requisicao.full_clean()
            requisicao.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render_form(itens_form, manutencoes_form)

        medida_provisoria = bool(requisicao.comprovante_pagamento)

        for material_id, quantidade, valor_dec in itens_validados:
            material = materiais[material_id]
            solicitacao = SolicitacaoMaterial(
                requisicao=requisicao,
                material=material,
                quantidade_solicitada=quantidade,
                solicitante=requisicao.solicitante,
                solicitante_usuario=request.user,
                unidade_destino=unidade_destino,
                justificativa=justificativa,
                status='entregue' if medida_provisoria else 'pendente',
            )
            if medida_provisoria:
                solicitacao.atendida_por = request.user
            solicitacao.full_clean()
            solicitacao.save()

            if medida_provisoria:
                v_unit = valor_dec if valor_dec and valor_dec > 0 else Decimal('0.01')
                PedidoCompra.objects.create(
                    solicitacao=solicitacao,
                    fornecedor='Fornecedor Não Informado (Provisório)',
                    valor_unitario=v_unit,
                    valor_total=(v_unit * quantidade).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                    status='concluido',
                    aprovado_por=request.user,
                    obs='Criado automaticamente via anexo de comprovante de pagamento na requisição (Medida Provisória).'
                )

        for equipamento_id, problema in manutencoes_validadas:
            SolicitacaoManutencao.objects.create(
                requisicao=requisicao,
                equipamento=equipamentos[equipamento_id],
                problema=problema,
                status='aguardando_manutencao' if medida_provisoria else 'pendente',
            )

        if not medida_provisoria:
            from core.approval_workflow import criar_fluxo_compras
            descricao = (
                f'Unidade: {requisicao.unidade_destino}\n'
                f'Quantidade de produtos: {len(itens_validados)}\n'
                f'Solicitações de manutenção: {len(manutencoes_validadas)}\n'
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
                return render_form(itens_form, manutencoes_form)
            messages.success(
                request,
                f'Requisição {requisicao.numero} criada e enviada para aprovação da Adriana.',
            )
        else:
            messages.warning(
                request,
                f'Aviso: A requisição {requisicao.numero} foi processada como Medida Provisória e os pedidos foram gerados como concluídos.'
            )
        if medida_provisoria and itens_validados:
            requisicao.status = 'pedido'
            requisicao.save(update_fields=['status', 'atualizado_em'])
        return redirect('detalhe_requisicao', pk=requisicao.pk)

    return render_form()


@login_required
def detalhe_requisicao(request, pk):
    requisicao = get_object_or_404(
        RequisicaoCompra.objects.select_related('solicitante_usuario').prefetch_related(
            'itens__material', 'itens__pedidos', 'manutencoes__equipamento'
        ),
        pk=pk,
    )
    itens = list(requisicao.itens.all())
    for item in itens:
        item.requisicao = requisicao
        item.tem_pedido_ativo = any(
            pedido.status != 'reprovado' for pedido in item.pedidos.all()
        )
    return render(request, 'compras/detalhe_requisicao.html', {
        'requisicao': requisicao,
        'itens': itens,
        'manutencoes': list(requisicao.manutencoes.all()),
        'total_itens': len(itens) + requisicao.manutencoes.count(),
        'total_estoque': sum(item.status == 'atendido_interno' for item in itens),
        'total_compra': sum(item.status == 'compra_externa' for item in itens),
        'pode_confirmar_entrega': _pode_confirmar_entrega(request.user),
    })


@login_required
def detalhe_solicitacao(request, pk):
    sol = get_object_or_404(
        SolicitacaoMaterial.objects.select_related('material', 'requisicao').prefetch_related('pedidos'),
        pk=pk,
    )
    pedidos = sol.pedidos.all()
    return render(request, 'compras/detalhe_solicitacao.html', {
        'solicitacao': sol,
        'pedidos': pedidos,
        'tem_pedido_ativo': pedidos.exclude(status='reprovado').exists(),
        'pode_confirmar_entrega': _pode_confirmar_entrega(request.user),
    })


@login_required
@require_POST
@access_required(
    permission='compras.change_solicitacaomaterial',
    profiles=('compras', 'gestor', 'estoque_compras'),
)
@transaction.atomic
def confirmar_entrega(request, pk):
    # Mesma ordem de bloqueio do fluxo de aprovação: pedido, depois solicitação.
    pedidos = list(PedidoCompra.objects.select_for_update().filter(solicitacao_id=pk).exclude(status='reprovado'))
    sol = get_object_or_404(SolicitacaoMaterial.objects.select_for_update(), pk=pk)
    if sol.status == 'entregue':
        messages.info(request, 'A entrega deste material já foi confirmada.')
    elif not sol.pode_confirmar_entrega or any(
        pedido.status not in PedidoCompra.STATUS_APOS_APROVACAO for pedido in pedidos
    ):
        messages.error(request, 'A entrega só pode ser confirmada após a aprovação final e a liberação do material.')
    else:
        sol.status = 'entregue'
        sol.atendida_por = request.user
        sol.save(update_fields=['status', 'atendida_por', 'atualizado_em'])
        for pedido in pedidos:
            pedido.status = 'concluido'
            pedido.save(update_fields=['status', 'atualizado_em'])
        from core.models import LogAtividade
        LogAtividade.objects.create(
            usuario=request.user, modulo='compras', acao='Entrega confirmada',
            url=request.path, detalhes=f'{sol.numero} | {sol.material.nome} | {sol.unidade_destino}',
        )
        messages.success(request, 'Entrega confirmada com sucesso.')
    if sol.requisicao_id:
        return redirect('detalhe_requisicao', pk=sol.requisicao_id)
    return redirect('detalhe_solicitacao', pk=sol.pk)


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
            status='pedido_emitido',
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

        SolicitacaoMaterial.objects.filter(pk=sol.pk).update(status='aguardando_entrega')
        if sol.requisicao_id and sol.requisicao.status == 'aprovada':
            RequisicaoCompra.objects.filter(pk=sol.requisicao_id).update(
                status='pedido', atualizado_em=timezone.now()
            )
        messages.success(request, 'Pedido gerado sem nova etapa de aprovação da RC.')
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


@login_required
@access_required(permission='compras.change_requisicaocompra', profiles=('compras', 'gestor', 'estoque_compras'))
@transaction.atomic
def editar_requisicao(request, pk):
    requisicao = get_object_or_404(RequisicaoCompra, pk=pk)
    
    if requisicao.status in {'aprovada', 'pedido'}:
        messages.error(request, 'Requisições aprovadas ou com pedido emitido não podem ser editadas.')
        return redirect('detalhe_requisicao', pk=requisicao.pk)
        
    def render_form(itens_form=None, manutencoes_form=None):
        if itens_form is None:
            itens_form = []
            for sol in requisicao.itens.all():
                # Tentar achar o pedido concluído caso haja medida provisória para preencher o valor
                valor = ''
                if requisicao.comprovante_pagamento:
                    pedido = sol.pedidos.filter(status='concluido').first()
                    if pedido and pedido.valor_unitario:
                        valor = str(pedido.valor_unitario).replace('.', ',')
                        
                itens_form.append({
                    'material_id': str(sol.material_id),
                    'quantidade': str(sol.quantidade_solicitada).replace('.', ','),
                    'valor': valor,
                })
            if not itens_form:
                itens_form = [{'material_id': '', 'quantidade': '1', 'valor': ''}]
        if manutencoes_form is None:
            manutencoes_form = [
                {'equipamento_id': str(item.equipamento_id), 'problema': item.problema}
                for item in requisicao.manutencoes.select_related('equipamento')
            ]
            post_data = {
                'unidade_destino': requisicao.unidade_destino,
                'justificativa': requisicao.justificativa,
            }
        else:
            post_data = request.POST if request.method == 'POST' else {}
            
        return render(request, 'compras/nova_solicitacao.html', {
            'materiais': Material.objects.exclude(categoria__in=('manutencao', 'ferramentas')),
            'equipamentos': EquipamentoManutencao.objects.filter(ativo=True),
            'post_data': post_data,
            'itens_form': itens_form,
            'manutencoes_form': manutencoes_form,
            'is_edit': True,
            'requisicao': requisicao,
        })

    if request.method == 'POST':
        materiais_post = request.POST.getlist('material')
        quantidades_post = request.POST.getlist('quantidade_solicitada')
        valores_post = request.POST.getlist('valor_unitario')
        justificativa = request.POST.get('justificativa', '').strip()
        unidade_destino = request.POST.get('unidade_destino', '').strip()
        equipamentos_post = request.POST.getlist('manutencao_equipamento')
        problemas_post = request.POST.getlist('manutencao_problema')
        manutencoes_form = []
        for indice in range(max(len(equipamentos_post), len(problemas_post))):
            equipamento_id = equipamentos_post[indice].strip() if indice < len(equipamentos_post) else ''
            problema = problemas_post[indice].strip() if indice < len(problemas_post) else ''
            if equipamento_id or problema:
                manutencoes_form.append({'equipamento_id': equipamento_id, 'problema': problema})
        
        total_linhas = max(len(materiais_post), len(quantidades_post))
        itens_form = []
        for indice in range(total_linhas):
            material_id = materiais_post[indice].strip() if indice < len(materiais_post) else ''
            quantidade = quantidades_post[indice].strip() if indice < len(quantidades_post) else ''
            valor = valores_post[indice].strip() if indice < len(valores_post) else ''
            if material_id or valor or (quantidade and quantidade != '1'):
                itens_form.append({
                    'material_id': material_id,
                    'quantidade': quantidade,
                    'valor': valor,
                })

        if not unidade_destino or not justificativa or not (itens_form or manutencoes_form):
            messages.error(request, 'Preencha a unidade, a justificativa e pelo menos um produto ou manutenção.')
            return render_form(itens_form or [{'material_id': '', 'quantidade': '1', 'valor': ''}], manutencoes_form)
        if len(unidade_destino) > 100:
            messages.error(request, 'A unidade de destino deve ter no máximo 100 caracteres.')
            return render_form(itens_form, manutencoes_form)
        if len(itens_form) > 30:
            messages.error(request, 'Cada requisição pode conter no máximo 30 produtos.')
            return render_form(itens_form[:30], manutencoes_form)
        if len(manutencoes_form) > 30:
            messages.error(request, 'Cada requisição pode conter no máximo 30 solicitações de manutenção.')
            return render_form(itens_form, manutencoes_form[:30])

        itens_validados = []
        materiais_ids = []
        for numero_linha, item in enumerate(itens_form, start=1):
            if not item['material_id'] or not item['quantidade']:
                messages.error(request, f'Informe o produto e a quantidade no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            try:
                material_id = int(item['material_id'])
                quantidade = Decimal(item['quantidade'].replace(',', '.'))
                SolicitacaoMaterial._meta.get_field('quantidade_solicitada').clean(quantidade, None)
            except (TypeError, ValueError, InvalidOperation, ValidationError):
                messages.error(request, f'Informe uma quantidade válida no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            if quantidade <= 0:
                messages.error(request, f'A quantidade do item {numero_linha} deve ser maior que zero.')
                return render_form(itens_form, manutencoes_form)
            if material_id in materiais_ids:
                messages.error(request, 'O mesmo produto não pode ser repetido na requisição.')
                return render_form(itens_form, manutencoes_form)
                
            valor_dec = None
            if item.get('valor'):
                try:
                    v_str = item['valor'].replace('R$', '').replace('.', '').replace(',', '.').strip()
                    valor_dec = Decimal(v_str)
                    if valor_dec < 0:
                        raise ValueError
                except:
                    messages.error(request, f'Informe um valor unitário válido no item {numero_linha}.')
                    return render_form(itens_form, manutencoes_form)
                    
            materiais_ids.append(material_id)
            itens_validados.append((material_id, quantidade, valor_dec))

        materiais = {
            material.pk: material
            for material in Material.objects.select_for_update().exclude(
                categoria__in=('manutencao', 'ferramentas')
            ).filter(pk__in=materiais_ids)
        }
        if len(materiais) != len(materiais_ids):
            messages.error(request, 'Um dos produtos selecionados não está mais disponível.')
            return render_form(itens_form, manutencoes_form)

        manutencoes_validadas = []
        for numero_linha, item in enumerate(manutencoes_form, start=1):
            if not item['equipamento_id'] or not item['problema']:
                messages.error(request, f'Informe o equipamento e a manutenção necessária no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            try:
                equipamento_id = int(item['equipamento_id'])
            except (TypeError, ValueError):
                messages.error(request, f'Selecione um equipamento válido no item {numero_linha}.')
                return render_form(itens_form, manutencoes_form)
            manutencoes_validadas.append((equipamento_id, item['problema']))
        equipamentos = {
            equipamento.pk: equipamento
            for equipamento in EquipamentoManutencao.objects.select_for_update().filter(
                pk__in=[item[0] for item in manutencoes_validadas], ativo=True
            )
        }
        if len(equipamentos) != len(manutencoes_validadas):
            messages.error(request, 'Um dos equipamentos não está mais disponível para solicitação.')
            return render_form(itens_form, manutencoes_form)

        requisicao.unidade_destino = unidade_destino
        requisicao.justificativa = justificativa
        from core.direct_uploads import assign_direct_upload
        
        try:
            if 'documento' in request.FILES:
                requisicao.documento = request.FILES['documento']
            else:
                assign_direct_upload(requisicao, request, 'documento')

            if 'comprovante_pagamento' in request.FILES:
                requisicao.comprovante_pagamento = request.FILES['comprovante_pagamento']
            else:
                assign_direct_upload(requisicao, request, 'comprovante_pagamento')

            if requisicao.comprovante_pagamento:
                requisicao.status = 'aprovada'
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))
            return render_form(itens_form, manutencoes_form)

        try:
            requisicao.full_clean()
            requisicao.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render_form(itens_form, manutencoes_form)

        # Deleta os itens anteriores (que ainda não viraram pedido ou estão pendentes)
        requisicao.itens.all().delete()
        requisicao.manutencoes.all().delete()

        medida_provisoria = bool(requisicao.comprovante_pagamento)

        for material_id, quantidade, valor_dec in itens_validados:
            material = materiais[material_id]
            solicitacao = SolicitacaoMaterial(
                requisicao=requisicao,
                material=material,
                quantidade_solicitada=quantidade,
                solicitante=requisicao.solicitante,
                solicitante_usuario=request.user,
                unidade_destino=unidade_destino,
                justificativa=justificativa,
                status='entregue' if medida_provisoria else 'pendente',
            )
            if medida_provisoria:
                solicitacao.atendida_por = request.user
            solicitacao.full_clean()
            solicitacao.save()

            if medida_provisoria:
                v_unit = valor_dec if valor_dec and valor_dec > 0 else Decimal('0.01')
                PedidoCompra.objects.create(
                    solicitacao=solicitacao,
                    fornecedor='Fornecedor Não Informado (Provisório)',
                    valor_unitario=v_unit,
                    valor_total=(v_unit * quantidade).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                    status='concluido',
                    aprovado_por=request.user,
                    obs='Criado automaticamente via anexo de comprovante de pagamento na requisição (Medida Provisória).'
                )

        for equipamento_id, problema in manutencoes_validadas:
            SolicitacaoManutencao.objects.create(
                requisicao=requisicao,
                equipamento=equipamentos[equipamento_id],
                problema=problema,
                status='aguardando_manutencao' if medida_provisoria else 'pendente',
            )

        if not medida_provisoria:
            from core.models import AprovacaoRegistro
            from core.approval_workflow import criar_fluxo_compras
            # Remove aprovacao antiga e cria nova
            AprovacaoRegistro.objects.filter(
                content_type__app_label='compras',
                content_type__model='requisicaocompra',
                object_id=requisicao.pk
            ).delete()
            
            descricao = (
                f'Unidade: {requisicao.unidade_destino}\n'
                f'Quantidade de produtos: {len(itens_validados)}\n'
                f'Solicitações de manutenção: {len(manutencoes_validadas)}\n'
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
                return render_form(itens_form, manutencoes_form)
            messages.success(
                request,
                f'Requisição {requisicao.numero} atualizada e reenviada para aprovação.'
            )
        else:
            messages.warning(
                request,
                f'Aviso: A requisição {requisicao.numero} foi processada como Medida Provisória e os pedidos foram gerados como concluídos.'
            )
        return redirect('detalhe_requisicao', pk=requisicao.pk)

    return render_form()


@login_required
@access_required(permission='compras.delete_requisicaocompra', profiles=('compras', 'gestor', 'estoque_compras'))
@require_POST
@transaction.atomic
def excluir_requisicao(request, pk):
    requisicao = get_object_or_404(RequisicaoCompra, pk=pk)
    if requisicao.status in {'aprovada', 'pedido'}:
        messages.error(request, 'Requisições aprovadas ou com pedido emitido não podem ser excluídas.')
        return redirect('detalhe_requisicao', pk=requisicao.pk)
    
    from core.models import AprovacaoRegistro
    AprovacaoRegistro.objects.filter(
        content_type__app_label='compras',
        content_type__model='requisicaocompra',
        object_id=requisicao.pk
    ).delete()
    
    requisicao.delete()
    messages.success(request, 'Requisição excluída com sucesso.')
    return redirect('painel_compras')
