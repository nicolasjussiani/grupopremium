from hashlib import sha256
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from admissional.models import DocumentoAdmissional
from financeiro.models import DocumentoFinanceiro
from recrutamento.models import Candidato, Talento


LEGACY_FIELDS = (
    (DocumentoAdmissional, 'arquivo', 'arquivo_nuvem'),
    (Candidato, 'arquivo_pdf', 'arquivo'),
    (Talento, 'arquivo_pdf', 'arquivo'),
    (DocumentoFinanceiro, 'arquivo_pdf', 'arquivo'),
)


def _extension(instance):
    filename = getattr(instance, 'arquivo_nome', '') or ''
    extension = Path(filename).suffix.lower()
    if extension in {'.pdf', '.png', '.jpg', '.jpeg'}:
        return extension
    mimetype = getattr(instance, 'arquivo_mimetype', '') or ''
    return {
        'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg',
    }.get(mimetype, '.pdf')


def _storage_digest(field_file):
    digest = sha256()
    with field_file.storage.open(field_file.name, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.digest()


class Command(BaseCommand):
    help = 'Copia binarios legados do PostgreSQL para o Storage e, apos conferir, limpa o legado.'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', help='Executa as copias verificadas.')
        parser.add_argument('--limpar-legado', action='store_true', help='Limpa o binario apenas apos comparar o hash.')

    def handle(self, *args, **options):
        if options['limpar_legado'] and not options['execute']:
            raise CommandError('--limpar-legado exige --execute.')
        found = migrated = cleared = conflicts = 0
        for model, legacy_name, cloud_name in LEGACY_FIELDS:
            queryset = model.objects.exclude(**{legacy_name: None}).only('pk', legacy_name, cloud_name)
            for instance in queryset.iterator():
                legacy = bytes(getattr(instance, legacy_name) or b'')
                if not legacy:
                    continue
                found += 1
                cloud = getattr(instance, cloud_name)
                exists = bool(cloud and cloud.storage.exists(cloud.name))
                if options['execute'] and not exists:
                    cloud.save(f'legado-{instance.pk}{_extension(instance)}', ContentFile(legacy), save=False)
                    instance.save(update_fields=[cloud_name])
                    instance.refresh_from_db(fields=[cloud_name])
                    cloud = getattr(instance, cloud_name)
                    exists = bool(cloud and cloud.storage.exists(cloud.name))
                    migrated += 1
                if not options['execute']:
                    continue
                if not exists or _storage_digest(cloud) != sha256(legacy).digest():
                    conflicts += 1
                    self.stderr.write(self.style.ERROR(f'Hash divergente: {model._meta.label}#{instance.pk}'))
                    continue
                if options['limpar_legado']:
                    type(instance).objects.filter(pk=instance.pk).update(**{legacy_name: None})
                    cleared += 1
        mode = 'Simulacao' if not options['execute'] else 'Execucao'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: {found} legado(s), {migrated} migrado(s), '
            f'{cleared} limpo(s), {conflicts} conflito(s).'
        ))
        if conflicts:
            raise CommandError('Existem arquivos com hash divergente; os binarios foram preservados.')
