import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.services.processamento_storage import indexar_storage, processar_todos


class Command(BaseCommand):
    help = 'Indexa todo o Storage, extrai dados localmente e cria vínculos idempotentes.'

    def add_arguments(self, parser):
        parser.add_argument('--usuario', default='ceo_premium')
        parser.add_argument('--limite', type=int)
        parser.add_argument('--forcar', action='store_true')
        parser.add_argument('--sem-ocr', action='store_true')
        parser.add_argument('--somente-indexar', action='store_true')
        parser.add_argument('--somente-sem-texto', action='store_true')
        parser.add_argument('--workers', type=int, default=1)

    def handle(self, *args, **options):
        usuario = User.objects.filter(username=options['usuario']).first()
        if not usuario:
            raise CommandError(f'Usuário não encontrado: {options["usuario"]}')

        def progresso(mensagem):
            self.stdout.write(str(mensagem))

        resultado = {
            'indexacao': indexar_storage(usuario=usuario, progresso=progresso),
        }
        if not options['somente_indexar']:
            resultado['processamento'] = processar_todos(
                usuario=usuario,
                usar_ocr=not options['sem_ocr'],
                forcar=options['forcar'],
                limite=options['limite'],
                somente_sem_texto=options['somente_sem_texto'],
                workers=options['workers'],
                progresso=progresso,
            )
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2))
        self.stdout.write(self.style.SUCCESS('Processamento do Storage concluído.'))
