from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.client_ip import normalizar_ip
from core.models import LogAtividade, PermissaoIP


class Command(BaseCommand):
    help = 'Marca um IP como aprovado no cadastro administrativo, sem alterar o acesso.'

    def add_arguments(self, parser):
        parser.add_argument('ip')

    def handle(self, *args, **options):
        address = normalizar_ip(options['ip'])
        if not address:
            raise CommandError('Informe um endereço IPv4 ou IPv6 válido.')
        from django.db import transaction
        with transaction.atomic():
            PermissaoIP.objects.update_or_create(ip_address=address, defaults={
                'status': 'aprovado', 'decidido_por': None, 'decidido_em': timezone.now(),
            })
            LogAtividade.objects.create(
                acao='Controle de IP: recuperação pelo console', modulo='sistema', detalhes=f'IP: {address}',
            )
        self.stdout.write(self.style.SUCCESS(f'IP {address} registrado como aprovado. Este status não interfere no acesso.'))
