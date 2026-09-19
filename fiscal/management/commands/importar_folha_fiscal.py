from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fiscal.services import gerar_pagamentos_fiscais, importar_folha_xlsx


class Command(BaseCommand):
    help = 'Importa uma planilha XLSX para a base Fiscal, com conciliação e rastreabilidade.'

    def add_arguments(self, parser):
        parser.add_argument('arquivo')
        parser.add_argument('--competencia', required=True, help='Competência no formato AAAA-MM.')
        parser.add_argument(
            '--gerar-pagamentos',
            action='store_true',
            help='Gera pagamentos somente para linhas conciliadas e sem pendências.',
        )

    def handle(self, *args, **options):
        path = Path(options['arquivo']).resolve()
        if not path.is_file():
            raise CommandError(f'Arquivo não encontrado: {path}')
        try:
            competence = datetime.strptime(options['competencia'], '%Y-%m').date().replace(day=1)
        except ValueError as exc:
            raise CommandError('Competência inválida. Use AAAA-MM.') from exc
        try:
            folha, created = importar_folha_xlsx(
                content=path.read_bytes(),
                filename=path.name,
                competencia=competence,
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        action = 'importada' if created else 'já existente'
        self.stdout.write(self.style.SUCCESS(
            f'Folha {action}: id={folha.pk}; itens={folha.itens.count()}; '
            f'benefícios={folha.beneficios.count()}; status={folha.status}.'
        ))
        if options['gerar_pagamentos']:
            generated, skipped = gerar_pagamentos_fiscais(folha)
            self.stdout.write(self.style.SUCCESS(
                f'Pagamentos gerados={generated}; ignorados={skipped}.'
            ))
