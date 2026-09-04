from pathlib import Path

from django.core.exceptions import ValidationError


MAX_UPLOAD_SIZE = 10 * 1024 * 1024


def validate_document_upload(upload):
    _validate_upload(
        upload,
        extensions={'.pdf', '.png', '.jpg', '.jpeg'},
        mime_types={'application/pdf', 'image/png', 'image/jpeg'},
    )


def validate_image_upload(upload):
    _validate_upload(
        upload,
        extensions={'.png', '.jpg', '.jpeg'},
        mime_types={'image/png', 'image/jpeg'},
    )


def _validate_upload(upload, *, extensions, mime_types):
    if upload.size > MAX_UPLOAD_SIZE:
        raise ValidationError('O arquivo excede o limite de 10 MB.')
    extension = Path(upload.name).suffix.lower()
    if extension not in extensions:
        raise ValidationError('Extensao de arquivo nao permitida.')
    mime_type = getattr(upload, 'content_type', '')
    if mime_type not in mime_types:
        raise ValidationError('Tipo de arquivo nao permitido.')

    position = upload.tell()
    signature = upload.read(8)
    upload.seek(position)
    assinaturas = {
        '.pdf': (b'%PDF-', 'application/pdf'),
        '.png': (b'\x89PNG\r\n\x1a\n', 'image/png'),
        '.jpg': (b'\xff\xd8\xff', 'image/jpeg'),
        '.jpeg': (b'\xff\xd8\xff', 'image/jpeg'),
    }
    assinatura_esperada, mime_esperado = assinaturas[extension]
    if mime_type != mime_esperado or not signature.startswith(assinatura_esperada):
        raise ValidationError('Conteudo do arquivo invalido ou corrompido.')
