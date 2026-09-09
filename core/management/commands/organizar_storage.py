from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage

from core.storage_organization import (
    audit_storage_references,
    iter_file_models,
    organize_instance_files,
    quarantine_orphaned_files,
)


class Command(BaseCommand):
    help = 'Organiza todos os arquivos referenciados em caminhos canonicos.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o resultado sem alterar banco ou storage.',
        )
        parser.add_argument(
            '--quarentenar-orfaos',
            action='store_true',
            help='Move arquivos legados sem referencia para _orfaos/legado/.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        total_records = 0
        total_files = 0
        details = []

        for model in iter_file_models():
            model_records = 0
            model_files = 0
            for instance in model.objects.iterator():
                moved = organize_instance_files(instance, dry_run=dry_run)
                if moved:
                    model_records += 1
                    model_files += len(moved)
            if model_files:
                details.append(
                    f'{model._meta.label}: {model_files} arquivo(s) em '
                    f'{model_records} registro(s)'
                )
            total_records += model_records
            total_files += model_files

        for detail in details:
            self.stdout.write(detail)
        action = 'seriam reorganizados' if dry_run else 'foram reorganizados'
        self.stdout.write(
            self.style.SUCCESS(
                f'{total_files} arquivo(s) de {total_records} registro(s) '
                f'{action}.'
            )
        )

        audit = audit_storage_references()
        self.stdout.write(
            f"Auditoria: {audit['total']} referencia(s), "
            f"{len(audit['missing'])} ausente(s), "
            f"{len(audit['noncanonical'])} fora do padrao."
        )
        for reference in audit['missing']:
            self.stdout.write(self.style.ERROR(f'Ausente: {reference}'))

        if options['quarentenar_orfaos']:
            orphaned = quarantine_orphaned_files(
                default_storage, dry_run=dry_run
            )
            orphan_action = 'seriam movidos' if dry_run else 'foram movidos'
            self.stdout.write(
                self.style.SUCCESS(
                    f'{len(orphaned)} arquivo(s) orfao(s) {orphan_action} '
                    'para _orfaos/legado/.'
                )
            )
