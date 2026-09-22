"""Receipt validation and archival for manually entered payroll payments."""
from hashlib import sha256
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

from core.direct_uploads import verify_direct_upload
from core.models import ArquivoImportado
from core.storage_organization import copy_in_storage
from core.validators import validate_document_upload


def preparar_comprovante(request, pagamento):
    try:
        return _preparar_comprovante(request, pagamento)
    except (OSError, ValueError, BotoCoreError, ClientError) as exc:
        raise ValidationError('Não foi possível ler ou armazenar o comprovante. Selecione o arquivo novamente.') from exc


def _preparar_comprovante(request, pagamento):
    upload = request.FILES.get('comprovante_folha')
    key = verify_direct_upload(request, 'comprovante_folha')
    if not key and not upload:
        return None
    if upload:
        validate_document_upload(upload)
    nome = (request.POST.get('direct_upload_comprovante_folha_original_name') or Path(key).name) if key else upload.name
    nome = nome.replace('\\', '/').split('/')[-1].strip()[:255] or 'comprovante'
    digest = sha256()
    tamanho = 0
    source = default_storage.open(key, 'rb') if key else upload
    try:
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
            tamanho += len(chunk)
    finally:
        if key:
            source.close()
        else:
            source.seek(0)
    digest = digest.hexdigest()
    existente = ArquivoImportado.objects.filter(sha256=digest).first()
    if existente:
        if not pagamento.pk or existente.content_object != pagamento:
            raise ValidationError('Este comprovante já está cadastrado no Arquivo Central ou em outro pagamento.')
        return None
    extensao = Path(key if key else upload.name).suffix.lower()
    destino = f'arquivo_central/{digest[:2]}/{digest}{extensao}'
    try:
        destino = copy_in_storage(default_storage, key, destino) if key else default_storage.save(destino, upload)
    except (OSError, ValueError, BotoCoreError, ClientError) as exc:
        raise ValidationError('Não foi possível armazenar o comprovante. Tente novamente.') from exc
    return {
        'sha256': digest, 'arquivo': destino, 'nome_original': nome,
        'tamanho': tamanho,
        'mime_type': {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}[extensao],
    }


def vincular_comprovante(dados, pagamento, usuario):
    if dados is None:
        return
    arquivo, criado = ArquivoImportado.objects.get_or_create(
        sha256=dados['sha256'], defaults={
            **dados, 'categoria': 'pagamento_colaborador', 'subcategoria': pagamento.tipo,
            'area': 'financeiro', 'status': 'vinculado',
            'content_object': pagamento, 'importado_por': usuario,
            'data_documento': pagamento.data_pagamento or pagamento.data_vencimento,
            'metadados': {'origem': 'formulario_pagamento'},
        },
    )
    if not criado and arquivo.content_object != pagamento:
        raise ValidationError('Este comprovante já está vinculado a outro cadastro.')


def exigir_comprovante(dados, pagamento):
    if dados is None and not (pagamento.pk and pagamento.arquivos_importados.exists()):
        raise ValidationError('Anexe um comprovante para confirmar o pagamento.')
