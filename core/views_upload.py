import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.direct_uploads import create_direct_upload
from core.access import user_has_access


def _can_upload(user, field_name):
    if field_name.startswith('anexo_'):
        return user_has_access(user, profiles=('rh', 'sesmet'))
    rules = {
        'arquivo': {'profiles': ('rh', 'gestor')},
        'arquivo_pdf': {
            'groups': ('Financeiro_Operador', 'Financeiro_Auditor', 'Financeiro_Aprovador')
        },
        'curriculo_pdf': {'profiles': ('rh', 'gestor')},
        'foto': {'profiles': ('sesmet', 'compras', 'gestor')},
        'foto_equipamento': {'profiles': ('sesmet', 'compras', 'gestor')},
    }
    access = rules.get(field_name)
    return bool(access and user_has_access(user, **access))


@login_required
@require_POST
def presign_upload(request):
    if not settings.SUPABASE_S3_ENDPOINT_URL:
        return JsonResponse(
            {'error': 'Upload direto indisponivel neste ambiente.'}, status=503
        )
    try:
        data = json.loads(request.body)
        if not _can_upload(request.user, data.get('field', '')):
            return JsonResponse({'error': 'Sem permissao para este upload.'}, status=403)
        url, key, token = create_direct_upload(
            request.user,
            data.get('field', ''),
            data.get('filename', ''),
            data.get('content_type', ''),
            data.get('size'),
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) else 'Dados invalidos.'
        return JsonResponse({'error': message}, status=400)
    return JsonResponse({'upload_url': url, 'key': key, 'token': token})
