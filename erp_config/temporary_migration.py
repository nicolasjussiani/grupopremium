"""Temporary, superuser-only bridge for the pending production purchase migration."""

import logging
from io import StringIO

from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpResponse, HttpResponseForbidden
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


logger = logging.getLogger(__name__)
TARGET = ('compras', '0011_manutencao_sem_aprovacao_pedido')


@never_cache
@staff_member_required
@require_http_methods(['GET', 'POST'])
def apply_purchase_migration(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Acesso restrito ao superusuário.')

    executor = MigrationExecutor(connection)
    pending = executor.migration_plan([TARGET])
    if not pending:
        return HttpResponse('Migração de Compras 0011 já aplicada.', content_type='text/plain; charset=utf-8')

    if request.method == 'GET':
        token = get_token(request)
        return HttpResponse(
            '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<title>Migração de Compras</title><body>'
            '<h1>Migração de Compras pendente</h1>'
            '<p>Aplicar a migração 0011 e suas dependências no banco de produção.</p>'
            f'<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="{token}">'
            '<button type="submit">Aplicar migração</button></form></body></html>'
        )

    try:
        call_command('migrate', 'compras', TARGET[1], interactive=False, stdout=StringIO())
    except Exception:
        logger.exception('Falha ao aplicar a migração de Compras 0011')
        return HttpResponse('Falha na migração. Consulte os logs.', status=500, content_type='text/plain; charset=utf-8')

    if MigrationExecutor(connection).migration_plan([TARGET]):
        logger.error('A migração de Compras 0011 permanece pendente após migrate')
        return HttpResponse('Migração ainda pendente.', status=500, content_type='text/plain; charset=utf-8')
    return HttpResponse('Migração de Compras 0011 aplicada com sucesso.', content_type='text/plain; charset=utf-8')
