"""Uploads diretos e autenticados para o Supabase Storage (S3)."""
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename


DIRECT_UPLOAD_MAX_SIZE = 50 * 1024 * 1024
DIRECT_UPLOAD_TOKEN_MAX_AGE = 30 * 60
TOKEN_SALT = 'core.direct-upload.v1'

UPLOAD_RULES = {
    'arquivo': ('documentos_admissional', 'document'),
    'arquivo_pdf': ('notas_fiscais', 'document'),
    'curriculo_pdf': ('curriculos', 'document'),
    'foto': ('equipamentos', 'image'),
    'foto_equipamento': ('manutencao', 'image'),
}

DOCUMENT_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg'}
DOCUMENT_MIME_TYPES = {'application/pdf', 'image/png', 'image/jpeg'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
IMAGE_MIME_TYPES = {'image/png', 'image/jpeg'}


def upload_rule(field_name):
    if field_name.startswith('anexo_'):
        return 'colaboradores/docs', 'document'
    return UPLOAD_RULES.get(field_name)


def validate_upload_metadata(field_name, filename, content_type, size):
    rule = upload_rule(field_name)
    if not rule:
        raise ValidationError('Campo de upload nao permitido.')
    try:
        size = int(size)
    except (TypeError, ValueError):
        raise ValidationError('Tamanho de arquivo invalido.')
    if size <= 0 or size > DIRECT_UPLOAD_MAX_SIZE:
        raise ValidationError('O arquivo deve ter no maximo 50 MB.')

    extension = Path(filename).suffix.lower()
    kind = rule[1]
    allowed_extensions = IMAGE_EXTENSIONS if kind == 'image' else DOCUMENT_EXTENSIONS
    allowed_mime_types = IMAGE_MIME_TYPES if kind == 'image' else DOCUMENT_MIME_TYPES
    if extension not in allowed_extensions or content_type not in allowed_mime_types:
        raise ValidationError('Tipo de arquivo nao permitido.')
    return rule[0], extension, size


def create_direct_upload(user, field_name, filename, content_type, size):
    folder, extension, size = validate_upload_metadata(
        field_name, filename, content_type, size
    )
    safe_stem = get_valid_filename(Path(filename).stem)[:80] or 'arquivo'
    key = f'{folder}/{uuid4().hex}-{safe_stem}{extension}'
    client = boto3.client(
        's3',
        endpoint_url=settings.SUPABASE_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(signature_version='s3v4'),
    )
    url = client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
            'Key': key,
            'ContentType': content_type,
        },
        ExpiresIn=300,
        HttpMethod='PUT',
    )
    payload = {
        'uid': user.pk,
        'field': field_name,
        'key': key,
        'size': size,
        'content_type': content_type,
    }
    return url, key, signing.dumps(payload, salt=TOKEN_SALT, compress=True)


def verify_direct_upload(request, field_name, *, required=False):
    token = request.POST.get(f'direct_upload_{field_name}', '').strip()
    if not token:
        if required:
            raise ValidationError('Envie o arquivo solicitado.')
        return None
    try:
        payload = signing.loads(
            token, salt=TOKEN_SALT, max_age=DIRECT_UPLOAD_TOKEN_MAX_AGE
        )
    except signing.BadSignature:
        raise ValidationError('O envio do arquivo expirou. Selecione-o novamente.')
    if payload.get('uid') != request.user.pk or payload.get('field') != field_name:
        raise ValidationError('Referencia de arquivo invalida.')

    folder, extension, expected_size = validate_upload_metadata(
        field_name,
        payload.get('key', ''),
        payload.get('content_type', ''),
        payload.get('size'),
    )
    key = payload['key']
    if not key.startswith(f'{folder}/') or Path(key).suffix.lower() != extension:
        raise ValidationError('Caminho de arquivo invalido.')
    try:
        actual_size = default_storage.size(key)
        with default_storage.open(key, 'rb') as stored_file:
            signature = stored_file.read(8)
    except (OSError, ValueError, BotoCoreError, ClientError):
        raise ValidationError('O arquivo nao foi encontrado no armazenamento.')
    if actual_size != expected_size:
        raise ValidationError('O arquivo armazenado esta incompleto.')

    signatures = {
        '.pdf': b'%PDF-',
        '.png': b'\x89PNG\r\n\x1a\n',
        '.jpg': b'\xff\xd8\xff',
        '.jpeg': b'\xff\xd8\xff',
    }
    if not signature.startswith(signatures[extension]):
        raise ValidationError('Conteudo do arquivo invalido ou corrompido.')
    return key


def assign_direct_upload(instance, request, field_name, *, required=False):
    key = verify_direct_upload(request, field_name, required=required)
    if key:
        getattr(instance, field_name).name = key
    return key
