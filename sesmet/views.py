"""ERP Grupo PremiumBR — Views do Módulo 4: SESMET"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import IntegracaoSeguranca, RegistroEPI, OrdemServico, EquipamentoProtecao
from admissional.models import Colaborador
from core.models import LogAtividade

def registrar_log(usuario, acao, detalhes):
    if usuario.is_authenticated:
        LogAtividade.objects.create(usuario=usuario, acao=acao, detalhes=detalhes)

@login_required
def dashboard_sesmet(request):
    hoje = timezone.now().date()
    # Verifica epis que o colaborador retirou e não devolveu
    epis_vencidos = RegistroEPI.objects.filter(tipo_movimentacao='retirada', data_validade__lt=hoje)
    epis_vencendo = RegistroEPI.objects.filter(
        tipo_movimentacao='retirada',
        data_validade__gte=hoje,
        data_validade__lte=hoje + timezone.timedelta(days=7)
    )
    nao_assinados = RegistroEPI.objects.filter(tipo_movimentacao='retirada', assinado=False)
    
    return render(request, 'sesmet/dashboard.html', {
        'epis_vencidos': epis_vencidos,
        'epis_vencendo': epis_vencendo,
        'nao_assinados': nao_assinados,
        'total_colaboradores': Colaborador.objects.filter(status='ativo').count(),
        'total_epis_ativos': EquipamentoProtecao.objects.count(),
        'hoje': hoje,
    })

@login_required
def registrar_epi(request, colaborador_pk=None):
    colaborador = None
    if colaborador_pk:
        colaborador = get_object_or_404(Colaborador, pk=colaborador_pk)

    if request.method == 'POST':
        colab_pk = request.POST.get('colaborador') or colaborador_pk
        colab = get_object_or_404(Colaborador, pk=colab_pk)
        
        equip_pk = request.POST.get('equipamento')
        equipamento = get_object_or_404(EquipamentoProtecao, pk=equip_pk)
        
        from datetime import datetime
        data_movimentacao_str = request.POST['data_movimentacao']
        data_movimentacao_obj = datetime.strptime(data_movimentacao_str, '%Y-%m-%d').date()
        
        epi = RegistroEPI(
            colaborador=colab,
            equipamento=equipamento,
            tipo_movimentacao=request.POST.get('tipo_movimentacao', 'retirada'),
            data_movimentacao=data_movimentacao_obj,
            quantidade=int(request.POST.get('quantidade', 1)),
            registrado_por=request.user,
            obs=request.POST.get('obs', ''),
        )
        epi.save()
        
        registrar_log(request.user, "MOVIMENTACAO_EPI", f"{epi.get_tipo_movimentacao_display()} de {equipamento.nome} para {colab.nome}")
        
        messages.success(request,
            f'✅ Movimentação registrada: {epi.get_tipo_movimentacao_display()} de {equipamento.nome} para {colab.nome}.')
        return redirect('dashboard_sesmet')

    colaboradores = Colaborador.objects.filter(status='ativo')
    equipamentos = EquipamentoProtecao.objects.all()
    
    return render(request, 'sesmet/registrar_epi.html', {
        'colaborador': colaborador,
        'colaboradores': colaboradores,
        'equipamentos': equipamentos,
        'tipos_movimentacao': RegistroEPI.TIPO_MOVIMENTACAO,
    })

@login_required
def matriz_epis(request):
    hoje = timezone.now().date()
    colaboradores = Colaborador.objects.filter(status='ativo').prefetch_related('movimentacoes_epi')
    return render(request, 'sesmet/matriz_epis.html', {
        'colaboradores': colaboradores,
        'hoje': hoje,
    })

@login_required
def emitir_os(request, colaborador_pk):
    colaborador = get_object_or_404(Colaborador, pk=colaborador_pk)
    if request.method == 'POST':
        os_count = OrdemServico.objects.count() + 1
        os_num = f'OS-{os_count:04d}'
        os = OrdemServico(
            colaborador=colaborador,
            numero=os_num,
            descricao_riscos=request.POST['descricao_riscos'],
            medidas_preventivas=request.POST['medidas_preventivas'],
            epis_obrigatorios=request.POST['epis_obrigatorios'],
            data_emissao=timezone.now().date(),
            emitido_por=request.user,
        )
        os.save()
        messages.success(request, f'✅ Ordem de Serviço {os_num} emitida para {colaborador.nome}.')
        return redirect('dashboard_sesmet')
    return render(request, 'sesmet/emitir_os.html', {'colaborador': colaborador})


from .treinamentos_data import get_video_info

@login_required
def assinar_epi(request, epi_pk):
    epi = get_object_or_404(RegistroEPI, pk=epi_pk)
    video_info = get_video_info(epi.equipamento.nome.lower()) 

    if request.method == 'POST':
        assinatura_base64 = request.POST.get('assinatura_base64')
        if assinatura_base64:
            epi.assinado = True
            epi.assinatura_base64 = assinatura_base64
            epi.data_assinatura = timezone.now()
            epi.save()
            messages.success(request,
                f'✅ EPI assinado com sucesso por {epi.colaborador.nome}.')
            return redirect('matriz_epis')
        else:
            messages.warning(request, f'⚠️ Falha na assinatura. Assinatura não recebida.')
            return redirect('assinar_epi', epi_pk=epi.pk)
    
    return render(request, 'sesmet/assinar_epi.html', {'epi': epi, 'video_info': video_info})

@login_required
def recibo_epi(request, epi_pk):
    epi = get_object_or_404(RegistroEPI, pk=epi_pk)
    return render(request, 'sesmet/recibo_epi.html', {'epi': epi})

@login_required
def catalogo_equipamentos(request):
    equipamentos = EquipamentoProtecao.objects.all()
    return render(request, 'sesmet/catalogo_equipamentos.html', {'equipamentos': equipamentos})

@login_required
def novo_equipamento(request):
    if request.method == 'POST':
        equip = EquipamentoProtecao(
            nome=request.POST['nome'],
            numero_ca=request.POST.get('numero_ca', ''),
            fabricante=request.POST.get('fabricante', ''),
            validade_ca=request.POST.get('validade_ca') or None,
            dias_durabilidade=int(request.POST.get('dias_durabilidade', 30)),
            estoque_atual=int(request.POST.get('estoque_atual', 0))
        )
        equip.save()
        registrar_log(request.user, "CADASTRO_EPI", f"EPI {equip.nome} cadastrado.")
        messages.success(request, f'✅ Equipamento {equip.nome} cadastrado com sucesso!')
        return redirect('catalogo_equipamentos')
    return render(request, 'sesmet/form_equipamento.html')

@login_required
def editar_equipamento(request, pk):
    equip = get_object_or_404(EquipamentoProtecao, pk=pk)
    if request.method == 'POST':
        equip.nome = request.POST['nome']
        equip.numero_ca = request.POST.get('numero_ca', '')
        equip.fabricante = request.POST.get('fabricante', '')
        equip.validade_ca = request.POST.get('validade_ca') or None
        equip.dias_durabilidade = int(request.POST.get('dias_durabilidade', 30))
        equip.estoque_atual = int(request.POST.get('estoque_atual', 0))
        equip.save()
        registrar_log(request.user, "EDICAO_EPI", f"EPI {equip.nome} editado.")
        messages.success(request, f'✅ Equipamento {equip.nome} atualizado.')
        return redirect('catalogo_equipamentos')
    return render(request, 'sesmet/form_equipamento.html', {'equip': equip})
