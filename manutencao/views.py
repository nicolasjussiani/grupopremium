from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Ativo, RegistroManutencao
from core.access import access_required
from core.validators import validate_image_upload
from core.direct_uploads import verify_direct_upload
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal, InvalidOperation

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
@access_required(permission='manutencao.add_ativo', profiles=('sesmet', 'compras', 'gestor'))
@transaction.atomic
def novo_ativo(request):
    if request.method == 'POST':
        if any(not request.POST.get(field, '').strip() for field in ('numero_patrimonio', 'nome', 'unidade_atual')):
            messages.error(request, 'Preencha patrimonio, nome e unidade.')
            return render(request, 'manutencao/form_ativo.html')
        status = request.POST.get('status', 'ativo')
        status_validos = {value for value, _ in Ativo.STATUS}
        if status not in status_validos:
            messages.error(request, 'Status do ativo invalido.')
            return render(request, 'manutencao/form_ativo.html')
        foto = request.FILES.get('foto')
        try:
            direct_key = verify_direct_upload(request, 'foto')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return render(request, 'manutencao/form_ativo.html')
        if foto:
            try:
                validate_image_upload(foto)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'manutencao/form_ativo.html')
        ativo = Ativo(
            numero_patrimonio=request.POST['numero_patrimonio'],
            nome=request.POST['nome'],
            marca=request.POST.get('marca', ''),
            modelo=request.POST.get('modelo', ''),
            numero_serie=request.POST.get('numero_serie', ''),
            descricao=request.POST.get('descricao', ''),
            unidade_atual=request.POST['unidade_atual'],
            status=status,
            foto=foto,
        )
        if direct_key:
            ativo.foto.name = direct_key
        data_aquisicao = request.POST.get('data_aquisicao')
        if data_aquisicao:
            ativo.data_aquisicao = data_aquisicao
        
        valor_aquisicao = request.POST.get('valor_aquisicao')
        if valor_aquisicao:
            try:
                ativo.valor_aquisicao = Decimal(valor_aquisicao.replace(',', '.'))
            except InvalidOperation:
                messages.error(request, 'Valor de aquisicao invalido.')
                return render(request, 'manutencao/form_ativo.html')
            if ativo.valor_aquisicao < 0:
                messages.error(request, 'O valor de aquisicao nao pode ser negativo.')
                return render(request, 'manutencao/form_ativo.html')

        try:
            ativo.full_clean()
            ativo.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'manutencao/form_ativo.html')
        except OSError:
            transaction.set_rollback(True)
            messages.error(request, 'Nao foi possivel armazenar a foto do ativo.')
            return render(request, 'manutencao/form_ativo.html')
        messages.success(request, f'✅ Ativo {ativo.numero_patrimonio} cadastrado com sucesso!')
        return redirect('lista_ativos')
    return render(request, 'manutencao/form_ativo.html')

@login_required
@access_required(permission='manutencao.change_ativo', profiles=('sesmet', 'compras', 'gestor'))
@transaction.atomic
def editar_ativo(request, pk):
    ativo = get_object_or_404(Ativo.objects.select_for_update(), pk=pk)
    if request.method == 'POST':
        if any(not request.POST.get(field, '').strip() for field in ('numero_patrimonio', 'nome', 'unidade_atual')):
            messages.error(request, 'Preencha patrimonio, nome e unidade.')
            return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})
        status = request.POST.get('status', 'ativo')
        if status not in {value for value, _ in Ativo.STATUS}:
            messages.error(request, 'Status do ativo invalido.')
            return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})
        ativo.numero_patrimonio = request.POST['numero_patrimonio']
        ativo.nome = request.POST['nome']
        ativo.marca = request.POST.get('marca', '')
        ativo.modelo = request.POST.get('modelo', '')
        ativo.numero_serie = request.POST.get('numero_serie', '')
        ativo.descricao = request.POST.get('descricao', '')
        ativo.unidade_atual = request.POST['unidade_atual']
        ativo.status = status
        
        if 'foto' in request.FILES:
            try:
                validate_image_upload(request.FILES['foto'])
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})
            ativo.foto = request.FILES['foto']
        else:
            try:
                direct_key = verify_direct_upload(request, 'foto')
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})
            if direct_key:
                ativo.foto.name = direct_key
        
        data_aquisicao = request.POST.get('data_aquisicao')
        ativo.data_aquisicao = data_aquisicao or None
            
        valor_aquisicao = request.POST.get('valor_aquisicao')
        try:
            ativo.valor_aquisicao = (
                Decimal(valor_aquisicao.replace(',', '.')) if valor_aquisicao else None
            )
        except InvalidOperation:
            messages.error(request, 'Valor de aquisicao invalido.')
            return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})
        if ativo.valor_aquisicao is not None and ativo.valor_aquisicao < 0:
            messages.error(request, 'O valor de aquisicao nao pode ser negativo.')
            return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})

        try:
            ativo.full_clean()
            ativo.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})
        except OSError:
            transaction.set_rollback(True)
            messages.error(request, 'Nao foi possivel armazenar a foto do ativo.')
            return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})
        messages.success(request, f'✅ Ativo {ativo.numero_patrimonio} atualizado.')
        return redirect('lista_ativos')
    return render(request, 'manutencao/form_ativo.html', {'ativo': ativo})

@login_required
def lista_manutencoes(request):
    manutencoes = RegistroManutencao.objects.all()
    return render(request, 'manutencao/lista_manutencoes.html', {'manutencoes': manutencoes})

@login_required
@access_required(permission='manutencao.add_registromanutencao', profiles=('sesmet', 'compras', 'gestor'))
@transaction.atomic
def nova_manutencao(request):
    if request.method == 'POST':
        if any(not request.POST.get(field, '').strip() for field in ('ativo', 'unidade_origem', 'motivo', 'data_inicio')):
            messages.error(request, 'Preencha ativo, unidade, motivo e data de inicio.')
            return redirect('nova_manutencao')
        ativo = get_object_or_404(Ativo.objects.select_for_update(), pk=request.POST['ativo'], status='ativo')
        foto = request.FILES.get('foto_equipamento')
        try:
            direct_key = verify_direct_upload(request, 'foto_equipamento')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect('nova_manutencao')
        if foto:
            try:
                validate_image_upload(foto)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect('nova_manutencao')
        
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
            registrado_por=request.user,
            foto_equipamento=foto,
        )
        if direct_key:
            manut.foto_equipamento.name = direct_key
        try:
            manut.full_clean()
            manut.save()
        except ValidationError as exc:
            transaction.set_rollback(True)
            messages.error(request, '; '.join(exc.messages))
            return redirect('nova_manutencao')
        except OSError:
            transaction.set_rollback(True)
            messages.error(request, 'Nao foi possivel armazenar a foto da manutencao.')
            return redirect('nova_manutencao')
        
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
@access_required(permission='manutencao.change_registromanutencao', profiles=('sesmet', 'compras', 'gestor'))
@transaction.atomic
def concluir_manutencao(request, pk):
    manut = get_object_or_404(RegistroManutencao.objects.select_for_update(), pk=pk)
    if request.method == 'POST':
        novo_status = request.POST.get('status', 'concluida')
        if novo_status not in {'andamento', 'concluida', 'cancelada'}:
            messages.error(request, 'Status de manutencao invalido.')
            return redirect('lista_manutencoes')
        manut.status = novo_status
        manut.data_conclusao = (
            request.POST.get('data_conclusao') or timezone.now().date()
            if novo_status in {'concluida', 'cancelada'} else None
        )
        manut.fornecedor_servico = request.POST.get('fornecedor_servico', '')
        manut.obs = request.POST.get('obs', '')
        
        custo = request.POST.get('custo_reparo')
        try:
            manut.custo_reparo = Decimal(custo.replace(',', '.')) if custo else None
        except InvalidOperation:
            messages.error(request, 'Custo de reparo invalido.')
            return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})
        if manut.custo_reparo is not None and manut.custo_reparo < 0:
            messages.error(request, 'O custo de reparo nao pode ser negativo.')
            return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})
            
        if 'foto_equipamento' in request.FILES:
            try:
                validate_image_upload(request.FILES['foto_equipamento'])
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})
            manut.foto_equipamento = request.FILES['foto_equipamento']
        else:
            try:
                direct_key = verify_direct_upload(request, 'foto_equipamento')
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})
            if direct_key:
                manut.foto_equipamento.name = direct_key
            
        try:
            manut.full_clean()
            manut.save()
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})
        except OSError:
            transaction.set_rollback(True)
            messages.error(request, 'Nao foi possivel armazenar a foto da manutencao.')
            return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})

        if manut.status in {'concluida', 'cancelada'}:
            ativo = Ativo.objects.select_for_update().get(pk=manut.ativo_id)
            ativo.status = 'ativo'
            ativo.unidade_atual = request.POST.get('unidade_retorno', manut.unidade_origem)
            ativo.save()
            messages.success(request, f'✅ Manutenção concluída. O ativo retornou para uso.')
        else:
            messages.success(request, f'✅ Manutenção atualizada.')
            
        return redirect('lista_manutencoes')
    
    return render(request, 'manutencao/form_concluir_manutencao.html', {'manutencao': manut})
