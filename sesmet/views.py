"""ERP Grupo PremiumBR — Views do Módulo 4: SESMET"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import IntegracaoSeguranca, RegistroEPI, OrdemServico, EquipamentoProtecao
from admissional.models import Colaborador
from core.models import LogAtividade
from core.access import access_required
from core.direct_uploads import assign_direct_upload
from core.validators import validate_image_upload
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
import base64
import binascii
import uuid

from .services import sincronizar_alertas_epi


logger = logging.getLogger(__name__)

def registrar_log(usuario, acao, detalhes):
    if usuario.is_authenticated:
        LogAtividade.objects.create(usuario=usuario, acao=acao, detalhes=detalhes)


def _aplicar_foto_equipamento(equipamento, request):
    """Aceita foto pequena pelo Django ou upload grande direto ao Storage."""
    arquivo = request.FILES.get('foto')
    if arquivo:
        validate_image_upload(arquivo)
        equipamento.foto = arquivo
    chave_direta = assign_direct_upload(equipamento, request, 'foto')
    if not arquivo and not chave_direta and request.POST.get('foto-clear'):
        equipamento.foto = None

@login_required
def dashboard_sesmet(request):
    hoje = timezone.localdate()
    try:
        sincronizar_alertas_epi()
    except Exception:
        logger.exception('Falha ao sincronizar alertas de EPI')
    # Verifica epis que o colaborador retirou e não devolveu
    epis_ativos = RegistroEPI.objects.filter(
        tipo_movimentacao='retirada', ciclo_ativo=True
    ).select_related('colaborador', 'equipamento', 'registrado_por')
    epis_vencidos = epis_ativos.filter(data_validade__lt=hoje)
    epis_vencendo = epis_ativos.filter(
        data_validade__gte=hoje,
        data_validade__lte=hoje + timezone.timedelta(days=15)
    )
    
    return render(request, 'sesmet/dashboard.html', {
        'epis_vencidos': epis_vencidos,
        'epis_vencendo': epis_vencendo,
        'total_colaboradores': Colaborador.objects.filter(status='ativo').count(),
        'total_epis_ativos': EquipamentoProtecao.objects.count(),
        'hoje': hoje,
    })

@login_required
@access_required(permission='sesmet.add_registroepi', profiles=('sesmet', 'gestor'))
@transaction.atomic
def registrar_epi(request, colaborador_pk=None):
    colaborador = None
    if colaborador_pk:
        colaborador = get_object_or_404(Colaborador, pk=colaborador_pk)

    if request.method == 'POST':
        colab_pk = request.POST.get('colaborador') or colaborador_pk
        if not colab_pk or not request.POST.get('equipamento'):
            messages.error(request, 'Selecione o colaborador e o equipamento.')
            return redirect('registrar_epi')
        colab = get_object_or_404(Colaborador, pk=colab_pk)
        
        equip_pk = request.POST.get('equipamento')
        equipamento = get_object_or_404(EquipamentoProtecao, pk=equip_pk)
        
        epi = RegistroEPI(
            colaborador=colab,
            equipamento=equipamento,
            tipo_movimentacao='retirada',
            data_movimentacao=timezone.localdate(),
            quantidade=1,
            registrado_por=request.user,
        )
        try:
            epi.save()
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect('registrar_epi')
        
        registrar_log(request.user, "ENTREGA_EPI", f"Entrega de {equipamento.nome} para {colab.nome}")
        
        messages.success(request,
            f'✅ Entrega confirmada: {equipamento.nome} para {colab.nome}. '
            f'O ciclo de 90 dias termina em {epi.data_validade:%d/%m/%Y}.')
        return redirect('dashboard_sesmet')

    colaboradores = Colaborador.objects.filter(status='ativo')
    equipamentos = EquipamentoProtecao.objects.filter(estoque_atual__gt=0)
    
    return render(request, 'sesmet/registrar_epi.html', {
        'colaborador': colaborador,
        'colaboradores': colaboradores,
        'equipamentos': equipamentos,
    })

@login_required
def matriz_epis(request):
    hoje = timezone.localdate()
    colaboradores = Colaborador.objects.filter(status='ativo').prefetch_related(
        Prefetch(
            'movimentacoes_epi',
            queryset=RegistroEPI.objects.filter(
                tipo_movimentacao='retirada', ciclo_ativo=True
            ).select_related('equipamento', 'registrado_por'),
            to_attr='epis_ativos',
        )
    )
    return render(request, 'sesmet/matriz_epis.html', {
        'colaboradores': colaboradores,
        'hoje': hoje,
    })

@login_required
@access_required(permission='sesmet.add_ordemservico', profiles=('sesmet', 'gestor'))
def emitir_os(request, colaborador_pk):
    colaborador = get_object_or_404(Colaborador, pk=colaborador_pk)
    if request.method == 'POST':
        campos = ('descricao_riscos', 'medidas_preventivas', 'epis_obrigatorios')
        if any(not request.POST.get(campo, '').strip() for campo in campos):
            messages.error(request, 'Preencha os riscos, medidas preventivas e EPIs obrigatorios.')
            return render(request, 'sesmet/emitir_os.html', {'colaborador': colaborador})
        os_num = f'OS-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}'
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
@access_required(permission='sesmet.change_registroepi', profiles=('sesmet', 'gestor'))
@transaction.atomic
def assinar_epi(request, epi_pk):
    epi = get_object_or_404(RegistroEPI.objects.select_for_update(), pk=epi_pk)
    video_info = get_video_info(epi.equipamento.nome.lower()) 

    if request.method == 'POST':
        assinatura_base64 = request.POST.get('assinatura_base64')
        if assinatura_base64:
            try:
                header, encoded = assinatura_base64.split(',', 1)
                if header != 'data:image/png;base64':
                    raise ValueError
                assinatura_bytes = base64.b64decode(encoded, validate=True)
                if (
                    len(assinatura_bytes) > 1024 * 1024
                    or not assinatura_bytes.startswith(b'\x89PNG\r\n\x1a\n')
                ):
                    raise ValueError
            except (ValueError, binascii.Error):
                messages.error(request, 'Assinatura invalida ou maior que 1 MB.')
                return redirect('assinar_epi', epi_pk=epi.pk)
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
@access_required(permission='sesmet.add_equipamentoprotecao', profiles=('sesmet', 'gestor', 'estoque_compras'))
def novo_equipamento(request):
    if request.method == 'POST':
        try:
            estoque_atual = int(request.POST.get('estoque_atual', 0))
        except (TypeError, ValueError):
            estoque_atual = -1
        if estoque_atual < 0 or not request.POST.get('nome', '').strip():
            messages.error(request, 'Nome ou estoque inválido.')
            return render(request, 'sesmet/form_equipamento.html', {'equip': None})
        equip = EquipamentoProtecao(
            nome=request.POST['nome'],
            numero_ca=request.POST.get('numero_ca', ''),
            fabricante=request.POST.get('fabricante', ''),
            validade_ca=request.POST.get('validade_ca') or None,
            dias_durabilidade=90,
            estoque_atual=estoque_atual,
        )
        try:
            _aplicar_foto_equipamento(equip, request)
            equip.full_clean()
            equip.save()
        except (ValidationError, OSError) as exc:
            mensagem = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, mensagem or 'Não foi possível salvar a foto.')
            return render(request, 'sesmet/form_equipamento.html', {'equip': None})
        registrar_log(request.user, "CADASTRO_EPI", f"EPI {equip.nome} cadastrado.")
        messages.success(request, f'✅ Equipamento {equip.nome} cadastrado com sucesso!')
        return redirect('catalogo_equipamentos')
    return render(request, 'sesmet/form_equipamento.html', {'equip': None})

@login_required
@access_required(permission='sesmet.change_equipamentoprotecao', profiles=('sesmet', 'gestor', 'estoque_compras'))
def editar_equipamento(request, pk):
    equip = get_object_or_404(EquipamentoProtecao, pk=pk)
    if request.method == 'POST':
        try:
            estoque_atual = int(request.POST.get('estoque_atual', 0))
        except (TypeError, ValueError):
            estoque_atual = -1
        if estoque_atual < 0 or not request.POST.get('nome', '').strip():
            messages.error(request, 'Nome ou estoque inválido.')
            return render(request, 'sesmet/form_equipamento.html', {'equip': equip})
        equip.nome = request.POST['nome']
        equip.numero_ca = request.POST.get('numero_ca', '')
        equip.fabricante = request.POST.get('fabricante', '')
        equip.validade_ca = request.POST.get('validade_ca') or None
        equip.dias_durabilidade = 90
        equip.estoque_atual = estoque_atual
        try:
            _aplicar_foto_equipamento(equip, request)
            equip.full_clean()
            equip.save()
        except (ValidationError, OSError) as exc:
            mensagem = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, mensagem or 'Não foi possível salvar a foto.')
            return render(request, 'sesmet/form_equipamento.html', {'equip': equip})
        registrar_log(request.user, "EDICAO_EPI", f"EPI {equip.nome} editado.")
        messages.success(request, f'✅ Equipamento {equip.nome} atualizado.')
        return redirect('catalogo_equipamentos')
    return render(request, 'sesmet/form_equipamento.html', {'equip': equip})
