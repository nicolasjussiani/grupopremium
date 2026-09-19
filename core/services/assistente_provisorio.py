"""Assistente local, sem API externa e sem permissao para gravacoes autonomas."""
import hashlib
from pathlib import Path

from django.core.files.storage import default_storage
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador, PresencaDiaria
from compras.models import PedidoCompra, SolicitacaoMaterial
from core.access import user_has_access, user_is_executive
from core.models import AprovacaoRegistro, ArquivoImportado
from core.services.importacao_arquivo_central import (
    classificar, classificar_pagamento_regra, extrair_beneficiario,
    extrair_data, extrair_identificador, extrair_valor, localizar_colaborador,
    nome_indicado,
)
from sesmet.models import RegistroEPI


MAX_ANALISE_LOCAL = 15 * 1024 * 1024


def _perfil(user):
    return getattr(getattr(user, 'perfil', None), 'perfil', 'operacional')


def categorias_permitidas(user):
    perfil = _perfil(user)
    if user_is_executive(user) or perfil in {'admin', 'gestor'}:
        return {value for value, _ in ArquivoImportado.CATEGORIAS}
    mapa = {
        'rh': {'pagamento_colaborador', 'reembolso', 'outro'},
        'financeiro': {'pagamento_colaborador', 'nota_fiscal', 'reembolso', 'planilha', 'outro'},
        'compras': {'nota_fiscal', 'pedido', 'planilha', 'outro'},
        'estoque_compras': {'nota_fiscal', 'pedido', 'planilha', 'outro'},
        'sesmet': {'outro'},
        'operacional': {'pedido', 'outro'},
    }
    return mapa.get(perfil, {'outro'})


def responder_pergunta(user, pergunta):
    """Responde com regras conhecidas e apenas indicadores agregados permitidos."""
    texto = ' '.join((pergunta or '').lower().split())[:500]
    perfil = _perfil(user)
    if not texto:
        return 'Digite uma pergunta sobre uma funcao, prazo ou indicador do ERP.'
    if any(termo in texto for termo in ('alterar', 'apagar', 'excluir', 'aprovar por mim', 'cadastrar por mim')):
        return ('Por seguranca, eu nao altero, excluo nem aprovo registros. Posso orientar o caminho '
                'e preparar dados de um documento para sua revisao.')
    if 'presen' in texto or 'falta' in texto:
        if user_has_access(user, profiles=('admin', 'rh', 'gestor', 'sesmet')):
            ultima = PresencaDiaria.objects.order_by('-data').values_list('data', flat=True).first()
            if not ultima:
                return 'Ainda nao ha lista de presenca utilizada. Linhas sem marcacao aparecem como Nao definido.'
            ativos = Colaborador.objects.filter(status='ativo').count()
            definidos = PresencaDiaria.objects.filter(data=ultima).exclude(status='indefinido').values('colaborador_id').distinct().count()
            return f'Na ultima data registrada ({ultima:%d/%m/%Y}), {max(ativos - definidos, 0)} de {ativos} colaboradores estao como Nao definido.'
        return 'A consulta de presenca esta disponivel apenas para RH, SESMET e gestores autorizados.'
    if 'epi' in texto or 'equipamento' in texto:
        if user_has_access(user, profiles=('admin', 'sesmet', 'gestor', 'estoque_compras')):
            ativos = RegistroEPI.objects.filter(ciclo_ativo=True, tipo_movimentacao='retirada').count()
            return f'Existem {ativos} ciclos de EPI ativos. Cada entrega inicia 90 dias e o alerta comeca 15 dias antes.'
        return 'Os dados de EPI sao restritos ao SESMET, gestores e responsaveis pelo estoque de EPI.'
    if any(termo in texto for termo in ('compra', 'pedido', 'requisi')):
        if user_has_access(user, profiles=('admin', 'compras', 'gestor', 'estoque_compras')):
            solicitacoes = SolicitacaoMaterial.objects.exclude(status__in=['atendido_interno', 'entregue', 'cancelado']).count()
            pedidos = PedidoCompra.objects.exclude(status__in=['entregue', 'cancelado']).count()
            return f'Compras possui {solicitacoes} solicitacao(oes) aberta(s) e {pedidos} pedido(s) ainda nao encerrado(s).'
        return 'Os detalhes de compras sao mostrados somente a usuarios autorizados nessa area.'
    if any(termo in texto for termo in ('pagamento', 'salario', 'vale transporte', 'ajuda de custo', 'financeir')):
        if user_has_access(user, profiles=('admin', 'rh', 'financeiro', 'gestor')):
            pendentes = PagamentoColaborador.objects.exclude(status__in=['pago', 'cancelado']).count()
            return f'Existem {pendentes} pagamento(s) ainda nao encerrado(s). CLT usa vale-transporte; PJ usa ajuda de custo.'
        return 'Os indicadores financeiros e da folha sao restritos ao RH, Financeiro e gestores autorizados.'
    if 'aprova' in texto:
        if user_is_executive(user) or perfil in {'admin', 'gestor'}:
            total = AprovacaoRegistro.objects.filter(status='pendente').count()
            return f'Ha {total} aprovacao(oes) pendente(s). Eu explico o processo, mas nunca aprovo em nome do usuario.'
        return 'Abra a area Aprovacoes para visualizar somente as etapas destinadas ao seu usuario.'
    if 'document' in texto or 'arquivo' in texto:
        return ('Envie o arquivo em "Ler documento". Sem chave de IA, PDFs com texto e nomes de arquivos '
                'sao classificados por regras locais. O resultado exige confirmacao humana.')
    if any(termo in texto for termo in ('como', 'onde', 'ajuda', 'usar')):
        return f'A Central de Ajuda possui o passo a passo de cada modulo: {reverse("ajuda")}. Tambem respondo sobre Presenca, EPI, Compras, Pagamentos, Documentos e Aprovacoes.'
    return ('No modo provisorio eu respondo sobre Presenca, EPI, Compras, Pagamentos, Documentos e Aprovacoes. '
            'A chave da IA ampliara perguntas abertas e leitura de imagens depois.')


def _texto_pdf(conteudo):
    try:
        import pymupdf
        with pymupdf.open(stream=conteudo, filetype='pdf') as documento:
            return '\n'.join(pagina.get_text() for pagina in documento)[:40000]
    except Exception:
        return ''


def registrar_documento(user, key, nome_original, content_type, categoria_solicitada=''):
    """Cria uma fila de revisao; nunca cria o objeto de negocio final sozinho."""
    tamanho = default_storage.size(key)
    digest = hashlib.sha256()
    conteudo = bytearray()
    with default_storage.open(key, 'rb') as stream:
        for bloco in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(bloco)
            if tamanho <= MAX_ANALISE_LOCAL:
                conteudo.extend(bloco)
    sha256 = digest.hexdigest()
    existente = ArquivoImportado.objects.filter(sha256=sha256).first()
    if existente:
        if existente.arquivo.name != key:
            default_storage.delete(key)
        return existente, False

    caminho = Path(nome_original)
    categoria, subcategoria = classificar(caminho)
    permitidas = categorias_permitidas(user)
    if categoria_solicitada in permitidas:
        categoria = categoria_solicitada
    elif categoria not in permitidas:
        categoria = 'outro'
    texto = _texto_pdf(bytes(conteudo)) if caminho.suffix.lower() == '.pdf' and conteudo else ''
    beneficiario = extrair_beneficiario(texto)
    valor = extrair_valor(texto)
    data_pagamento = extrair_data(texto, caminho.name)
    identificador = extrair_identificador(texto)
    colaborador = None
    if categoria in {'pagamento_colaborador', 'reembolso'}:
        indicado = nome_indicado(caminho, subcategoria)
        colaborador = localizar_colaborador(beneficiario or indicado, list(Colaborador.objects.all()))[0]
        subcategoria = classificar_pagamento_regra(subcategoria, data_pagamento, valor, colaborador)
    metadados = {
        'origem_assistente': True,
        'modo_analise': 'regras_locais_sem_api',
        'beneficiario': beneficiario,
        'valor': f'{valor:.2f}'.replace('.', ',') if valor is not None else '',
        'data_pagamento': data_pagamento.isoformat() if data_pagamento else '',
        'identificador_transacao': identificador,
        'colaborador_sugerido_id': colaborador.pk if colaborador else None,
    }
    metadados = {chave: valor_meta for chave, valor_meta in metadados.items() if valor_meta not in ('', None)}
    motivos = ['Importado pelo assistente provisorio; confirme os dados antes de vincular.']
    if not texto and caminho.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg'}:
        motivos.append('Texto nao extraido localmente; leitura visual aguardara a chave da IA ou revisao manual.')
    arquivo = ArquivoImportado(
        categoria=categoria, subcategoria=subcategoria, nome_original=nome_original[:255],
        sha256=sha256, tamanho=tamanho, mime_type=(content_type or '')[:120],
        status='revisar', motivo_revisao=' '.join(motivos), metadados=metadados,
        importado_por=user,
    )
    arquivo.arquivo.name = key
    arquivo.full_clean(exclude=('arquivo',))
    arquivo.save()
    return arquivo, True
