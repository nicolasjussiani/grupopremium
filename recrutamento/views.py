"""ERP Grupo Premium — Views do Módulo 1: Recrutamento e Seleção"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Vaga, Candidato, Talento
from admissional.models import Admissao, DocumentoAdmissional
from core.models import Notificacao
from django.contrib.auth.models import User
from django.http import JsonResponse
import json
import re
import io
import os

# OCR imports — opcionais (não disponíveis na Vercel)
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import pytesseract
    from PIL import Image
    import shutil
    # Configurar o caminho do Tesseract (instalado no Windows)
    tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        HAS_OCR = True
    elif shutil.which('tesseract'):
        HAS_OCR = True
    else:
        HAS_OCR = False
except ImportError:
    HAS_OCR = False


@login_required
def lista_vagas(request):
    vagas = Vaga.objects.all().prefetch_related('candidatos')
    status_filter = request.GET.get('status', '')
    if status_filter:
        vagas = vagas.filter(status=status_filter)
    context = {
        'vagas': vagas,
        'status_filter': status_filter,
        'status_choices': Vaga.STATUS_CHOICES,
        'total_vagas': Vaga.objects.count(),
        'vagas_abertas': Vaga.objects.exclude(status__in=['preenchida', 'cancelada']).count(),
    }
    return render(request, 'recrutamento/lista_vagas.html', context)


@login_required
def nova_vaga(request):
    if request.method == 'POST':
        # Gateway 1: Validar campos obrigatórios
        campos_obrigatorios = [
            'nome_vaga', 'quantidade_colaboradores', 'cidade', 'unidade',
            'perfil_desejado', 'atividades', 'horario_trabalho', 'tipo_contratacao',
            'valor_salario', 'previsao_inicio', 'motivo_solicitacao', 'gestor_responsavel'
        ]
        erros = []
        for campo in campos_obrigatorios:
            if not request.POST.get(campo, '').strip():
                erros.append(campo)

        if erros:
            messages.error(request,
                f'⚠️ GATEWAY: Informações incompletas! {len(erros)} campo(s) obrigatório(s) não preenchido(s).')
            return render(request, 'recrutamento/nova_vaga.html', {
                'post_data': request.POST,
                'erros': erros,
                'tipo_choices': Vaga.TIPO_CONTRATACAO,
            })

        vaga = Vaga(
            nome_vaga=request.POST['nome_vaga'],
            quantidade_colaboradores=int(request.POST['quantidade_colaboradores']),
            cidade=request.POST['cidade'],
            unidade=request.POST['unidade'],
            perfil_desejado=request.POST['perfil_desejado'],
            atividades=request.POST['atividades'],
            horario_trabalho=request.POST['horario_trabalho'],
            tipo_contratacao=request.POST['tipo_contratacao'],
            valor_salario=request.POST['valor_salario'],
            previsao_inicio=request.POST['previsao_inicio'],
            exige_experiencia=request.POST.get('exige_experiencia') == 'on',
            descricao_experiencia=request.POST.get('descricao_experiencia', ''),
            motivo_solicitacao=request.POST['motivo_solicitacao'],
            gestor_responsavel=request.POST['gestor_responsavel'],
            gestor_usuario=request.user,
            status='em_selecao',
        )
        vaga.save()
        messages.success(request, f'✅ Vaga "{vaga.nome_vaga}" criada com sucesso! Aguardando candidatos.')
        return redirect('detalhe_vaga', pk=vaga.pk)

    return render(request, 'recrutamento/nova_vaga.html', {
        'tipo_choices': Vaga.TIPO_CONTRATACAO,
    })


@login_required
def detalhe_vaga(request, pk):
    vaga = get_object_or_404(Vaga, pk=pk)
    candidatos = vaga.candidatos.all()
    candidatos_por_etapa = {
        'triagem': candidatos.filter(etapa_atual='triagem'),
        'avaliacao_dp': candidatos.filter(etapa_atual='avaliacao_dp'),
        'entrevista_final': candidatos.filter(etapa_atual='entrevista_final'),
        'aprovado': candidatos.filter(etapa_atual='aprovado'),
        'reprovado': candidatos.filter(etapa_atual='reprovado'),
    }
    return render(request, 'recrutamento/detalhe_vaga.html', {
        'vaga': vaga,
        'candidatos': candidatos,
        'candidatos_por_etapa': candidatos_por_etapa,
    })


@login_required
def adicionar_candidato(request, vaga_pk):
    vaga = get_object_or_404(Vaga, pk=vaga_pk)
    if request.method == 'POST':
        cpf = request.POST.get('cpf', '')
        email = request.POST.get('email', '')
        telefone = request.POST.get('telefone', '')
        nome = request.POST.get('nome', '')
        cidade = request.POST.get('cidade', '')

        candidato = Candidato(
            vaga=vaga,
            nome=nome,
            email=email,
            telefone=telefone,
            cidade=cidade,
            cpf=cpf,
            curriculum_obs=request.POST.get('curriculum_obs', ''),
            etapa_atual='triagem',
        )
        arquivo_pdf = request.FILES.get('curriculo_pdf')
        if arquivo_pdf:
            pdf_bytes = arquivo_pdf.read()
            candidato.arquivo_pdf = pdf_bytes
        candidato.save()
        
        # Salva no Banco de Talentos ou atualiza a última vaga aplicada
        if email:
            talento, created = Talento.objects.get_or_create(
                email=email,
                defaults={
                    'nome': nome,
                    'telefone': telefone,
                    'cidade': cidade,
                    'cpf': cpf,
                    'ultima_vaga': vaga
                }
            )
            if not created:
                talento.ultima_vaga = vaga
                talento.telefone = telefone
                talento.cidade = cidade
            if arquivo_pdf:
                talento.arquivo_pdf = pdf_bytes
            talento.save()

        messages.success(request, f'✅ Candidato {candidato.nome} adicionado à vaga {vaga.nome_vaga}.')
        return redirect('detalhe_vaga', pk=vaga_pk)
    return render(request, 'recrutamento/adicionar_candidato.html', {'vaga': vaga})


@login_required
def avancar_etapa(request, candidato_pk):
    """Gateway: avança candidato para próxima etapa ou reprova"""
    candidato = get_object_or_404(Candidato, pk=candidato_pk)
    if request.method == 'POST':
        acao = request.POST.get('acao')
        obs = request.POST.get('obs', '')
        etapas = ['triagem', 'avaliacao_dp', 'entrevista_final', 'aprovado']

        if acao == 'reprovar':
            candidato.etapa_atual = 'reprovado'
            candidato.aprovado = False
            candidato.save()
            messages.warning(request,
                f'❌ GATEWAY: Candidato {candidato.nome} reprovado. Processo retorna para nova seleção.')

        elif acao == 'avancar':
            idx = etapas.index(candidato.etapa_atual) if candidato.etapa_atual in etapas else 0
            if idx < len(etapas) - 1:
                candidato.etapa_atual = etapas[idx + 1]
                if candidato.etapa_atual == 'avaliacao_dp':
                    candidato.avaliacao_comportamental = obs
                elif candidato.etapa_atual == 'entrevista_final':
                    candidato.avaliacao_comportamental = obs
                elif candidato.etapa_atual == 'aprovado':
                    candidato.aprovado = True
                    candidato.resultado_entrevista = obs
                    # GATEWAY SIM → Dispara gatilho automático para Módulo 2
                    _disparar_admissao(candidato, request.user)
                candidato.save()
                messages.success(request, f'✅ Candidato {candidato.nome} avançou para: {candidato.get_etapa_atual_display()}')
            else:
                messages.info(request, 'Candidato já está na etapa final.')

        return redirect('detalhe_vaga', pk=candidato.vaga.pk)

    return render(request, 'recrutamento/gateway_candidato.html', {'candidato': candidato})


def _disparar_admissao(candidato, usuario):
    """Gatilho automático: candidato aprovado → cria processo admissional no Módulo 2"""
    if not candidato.encaminhado_admissao:
        admissao = Admissao(
            candidato_nome=candidato.nome,
            candidato_email=candidato.email,
            candidato_telefone=candidato.telefone,
            vaga_nome=candidato.vaga.nome_vaga,
            unidade_destino=candidato.vaga.unidade,
            status='aguardando_documentos',
            responsavel_rh=usuario,
        )
        admissao.save()

        # Criar checklist de documentos automaticamente
        tipos_doc = [t[0] for t in DocumentoAdmissional.TIPOS]
        for tipo in tipos_doc:
            DocumentoAdmissional.objects.create(admissao=admissao, tipo=tipo, status='pendente')

        candidato.encaminhado_admissao = True
        candidato.save()

        # Notificar RH
        for rh_user in User.objects.filter(perfil__perfil='rh'):
            Notificacao.objects.create(
                destinatario=rh_user,
                tipo='gateway',
                modulo='admissional',
                titulo=f'🔔 Novo candidato aprovado: {candidato.nome}',
                mensagem=f'Candidato {candidato.nome} foi aprovado para a vaga "{candidato.vaga.nome_vaga}" '
                         f'({candidato.vaga.unidade}). Processo admissional criado automaticamente.',
                url_acao=f'/admissional/{admissao.pk}/',
            )

@login_required
def banco_talentos(request):
    talentos = Talento.objects.all()
    cidade_filter = request.GET.get('cidade', '')
    nome_filter = request.GET.get('nome', '')
    vaga_filter = request.GET.get('vaga', '')
    
    if cidade_filter:
        talentos = talentos.filter(cidade__icontains=cidade_filter)
    if nome_filter:
        talentos = talentos.filter(nome__icontains=nome_filter)
    if vaga_filter:
        talentos = talentos.filter(ultima_vaga__nome_vaga__icontains=vaga_filter)
        
    return render(request, 'recrutamento/banco_talentos.html', {
        'talentos': talentos,
        'cidade_filter': cidade_filter,
        'nome_filter': nome_filter,
        'vaga_filter': vaga_filter,
    })

@login_required
def baixar_curriculo_candidato(request, pk):
    from django.http import HttpResponse, HttpResponseNotFound
    candidato = get_object_or_404(Candidato, pk=pk)
    if candidato.arquivo_pdf:
        response = HttpResponse(candidato.arquivo_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="curriculo_{candidato.nome}.pdf"'
        return response
    return HttpResponseNotFound("Currículo não encontrado.")

@login_required
def baixar_curriculo_talento(request, pk):
    from django.http import HttpResponse, HttpResponseNotFound
    talento = get_object_or_404(Talento, pk=pk)
    if talento.arquivo_pdf:
        response = HttpResponse(talento.arquivo_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="curriculo_{talento.nome}.pdf"'
        return response
    return HttpResponseNotFound("Currículo não encontrado.")

@login_required
def parse_curriculo(request):
    """Lê um PDF enviado por AJAX e tenta extrair nome, email e telefone."""
    if not HAS_FITZ:
        return JsonResponse({
            'error': 'Leitura de PDF não disponível neste servidor. Configure localmente para usar esta funcionalidade.'
        }, status=400)
    if request.method == 'POST' and request.FILES.get('curriculo'):
        arquivo = request.FILES['curriculo']
        texto = ""
        try:
            # Lê os bytes apenas uma vez
            file_bytes = arquivo.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                page_text = page.get_text()
                if len(page_text.strip()) > 5:
                    texto += page_text + "\n"
                else:
                    # OCR fallback para páginas escaneadas
                    if HAS_OCR:
                        try:
                            pix = page.get_pixmap(dpi=150)
                            img = Image.open(io.BytesIO(pix.tobytes()))
                            texto += pytesseract.image_to_string(img, lang='por') + "\n"
                        except Exception as ocr_e:
                            print(f"OCR ignorado na página: {ocr_e}")
            doc.close()
        except Exception as e:
            return JsonResponse({'error': 'Erro ao ler o PDF: ' + str(e)}, status=400)
            
        # Extração de Email
        # Corrige possíveis erros de OCR (ex: copyright ou grau lidos no lugar do @)
        texto_limpo = texto.replace('©', '@').replace('°', '@')
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', texto_limpo)
        email = email_match.group(0) if email_match else ''
        
        # Extração de Telefone (padrão básico Brasil)
        # Match para: (11) 99999-9999, 11 99999 9999, 11999999999, etc
        tel_match = re.search(r'\(?\d{2}\)?\s*9?\s*\d{4}[-\s]?\d{4}', texto)
        telefone = tel_match.group(0) if tel_match else ''
        
        # Extração de Nome
        nome = ""
        # 1. Tenta buscar um padrão explícito: "Nome: Fulano" ou "Nome completo: Fulano"
        nome_match = re.search(r'(?i)(?:nome\s*completo|nome):\s*([A-Za-zÀ-ÿ\s]+)', texto_limpo)
        if nome_match:
            nome = nome_match.group(1).strip()
        
        # 2. Se não encontrou padrão explícito, usa heurística da primeira linha
        if not nome or len(nome) < 3:
            linhas = [l.strip() for l in texto_limpo.split('\n') if len(l.strip()) > 2]
            # Ignora a palavra "Currículo" ou "Curriculum" se for a primeira linha
            if len(linhas) > 0:
                if linhas[0].lower() in ['currículo', 'curriculo', 'curriculum vitae', 'curriculum']:
                    linhas.pop(0)
                if len(linhas) > 0 and linhas[0].lower() in ['dados pessoais', 'dados pessoais:']:
                    linhas.pop(0)
            
            if len(linhas) > 0:
                nome = linhas[0]
                if len(nome) < 10 and len(linhas) > 1:
                    nome += " " + linhas[1]
        
        # Limpa caracteres bizarros do nome
        nome = re.sub(r'[^a-zA-ZáéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ \-]', '', nome).strip()
        
        if len(nome) > 100:
            nome = nome[:100]
            
        return JsonResponse({
            'nome': nome,
            'email': email,
            'telefone': telefone,
            'texto_extraido': texto
        })
        
    return JsonResponse({'error': 'Arquivo não enviado.'}, status=400)
