import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection


TABELAS = (
    'admissional_colaborador',
    'admissional_pagamentocolaborador',
    'admissional_documentocolaborador',
    'admissional_admissao',
    'fiscal_folhafiscal',
    'fiscal_itemfolhafiscal',
    'fiscal_beneficiofiscal',
    'fiscal_parcelabeneficiofiscal',
    'core_arquivoimportado',
    'core_origemarquivoimportado',
)


def _json(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return {'binario_bytes': len(valor)}
    return str(valor)


class Command(BaseCommand):
    help = 'Gera um backup JSON das tabelas alteradas pela importação do acervo.'

    def add_arguments(self, parser):
        parser.add_argument('--saida')

    def handle(self, *args, **options):
        destino = Path(options['saida'] or (
            Path('backups') / f'acervo-{datetime.now():%Y%m%d-%H%M%S}.json'
        )).resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        backup = {
            'gerado_em': datetime.now().isoformat(),
            'banco': connection.vendor,
            'tabelas': {},
        }
        tabelas_existentes = set(connection.introspection.table_names())
        with connection.cursor() as cursor:
            for tabela in TABELAS:
                if tabela not in tabelas_existentes:
                    backup['tabelas'][tabela] = {'ausente': True, 'registros': []}
                    continue
                quoted = connection.ops.quote_name(tabela)
                cursor.execute(f'SELECT * FROM {quoted} ORDER BY 1')
                colunas = [item[0] for item in cursor.description]
                registros = [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
                backup['tabelas'][tabela] = {
                    'quantidade': len(registros),
                    'registros': registros,
                }
        destino.write_text(
            json.dumps(backup, ensure_ascii=False, indent=2, default=_json),
            encoding='utf-8',
        )
        self.stdout.write(self.style.SUCCESS(f'Backup criado: {destino}'))
