import json
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.services.importacao_arquivo_central import ImportadorArquivoCentral


class Command(BaseCommand):
    help = 'Importa e organiza documentos no Arquivo Central sem duplicar conteúdo.'

    def add_arguments(self, parser):
        parser.add_argument('pasta')
        parser.add_argument('--usuario', help='Username responsável pela importação.')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limite', type=int)

    def handle(self, *args, **options):
        pasta = Path(options['pasta']).resolve()
        if not pasta.is_dir():
            raise CommandError(f'Pasta não encontrada: {pasta}')
        usuario = None
        if options['usuario']:
            usuario = User.objects.filter(username=options['usuario']).first()
            if not usuario:
                raise CommandError(f'Usuário não encontrado: {options["usuario"]}')
        importador = ImportadorArquivoCentral(
            pasta,
            usuario=usuario,
            dry_run=options['dry_run'],
            progresso=self.stdout.write,
        )
        resultado = importador.executar(limite=options['limite'])
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2))
        if resultado['erros']:
            raise CommandError('A importação terminou com erros; revise o resumo acima.')
        self.stdout.write(self.style.SUCCESS('Importação concluída.'))
