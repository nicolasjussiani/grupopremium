from django.core.management.base import BaseCommand

from admissional.models import Colaborador
from core.storage_organization import organize_instance_files


class Command(BaseCommand):
    help = 'Organiza anexos em uma pasta separada para cada colaborador.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra quantos anexos seriam reorganizados sem alterar o storage.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        colaboradores = 0
        arquivos = 0
        for colaborador in Colaborador.objects.iterator():
            moved = organize_instance_files(colaborador, dry_run=dry_run)
            if moved:
                colaboradores += 1
                arquivos += len(moved)

        action = 'seriam reorganizados' if dry_run else 'foram reorganizados'
        self.stdout.write(
            self.style.SUCCESS(
                f'{arquivos} arquivo(s) de {colaboradores} colaborador(es) '
                f'{action}.'
            )
        )
