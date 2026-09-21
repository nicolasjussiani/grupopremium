import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from admissional.models import PagamentoColaborador
from admissional.services.importacao_acervo import (
    localizar_folha_atual,
    registrar_distrato_documentado,
    sincronizar_colaboradores_xlsx,
)
from fiscal.services import decimal_value
from fiscal.models import FolhaFiscal
from fiscal.services import gerar_pagamentos_fiscais, importar_folha_xlsx


MESES = {
    'JANEIRO': 1,
    'FEVEREIRO': 2,
    'MARCO': 3,
    'ABRIL': 4,
    'MAIO': 5,
    'JUNHO': 6,
    'JULHO': 7,
    'AGOSTO': 8,
    'SETEMBRO': 9,
    'OUTUBRO': 10,
    'NOVEMBRO': 11,
    'DEZEMBRO': 12,
}


def _normalizar(valor):
    valor = unicodedata.normalize('NFKD', str(valor or ''))
    return ''.join(char for char in valor if not unicodedata.combining(char)).upper()


def inferir_competencia(caminho):
    texto = _normalizar(caminho)
    mes = next((numero for nome, numero in MESES.items() if nome in texto), None)
    anos = [int(ano) for ano in re.findall(r'(?<!\d)(20\d{2})(?!\d)', texto)]
    if not anos:
        abreviados = [int(ano) for ano in re.findall(r'(?<!\d)(2[5-9])(?!\d)', texto)]
        anos = [2000 + ano for ano in abreviados]
    if not mes or not anos:
        raise CommandError(
            f'Não foi possível inferir a competência de {caminho}. '
            'Informe no formato AAAA-MM=caminho.'
        )
    return datetime(max(anos), mes, 1).date()


def _parse_folha_historica(valor):
    if '=' not in valor:
        raise CommandError('Use --folha-historica AAAA-MM=caminho.xlsx.')
    competencia_texto, caminho_texto = valor.split('=', 1)
    try:
        competencia = datetime.strptime(competencia_texto, '%Y-%m').date()
    except ValueError as exc:
        raise CommandError('Competência histórica inválida. Use AAAA-MM.') from exc
    caminho = Path(caminho_texto).resolve()
    if not caminho.is_file():
        raise CommandError(f'Folha histórica não encontrada: {caminho}')
    return competencia, caminho


def _parse_desligamento_confirmado(valor):
    if '=' not in valor:
        raise CommandError('Use --desligamento-confirmado NOME=AAAA-MM-DD.')
    nome, data_texto = valor.rsplit('=', 1)
    try:
        data_desligamento = datetime.strptime(data_texto, '%Y-%m-%d').date()
    except ValueError as exc:
        raise CommandError('Data de desligamento invalida. Use AAAA-MM-DD.') from exc
    if not nome.strip():
        raise CommandError('Informe o nome antes da data de desligamento.')
    return nome.strip(), data_desligamento


def _parse_distrato_documentado(valor):
    partes = valor.split('|', 3)
    if len(partes) != 4:
        raise CommandError(
            'Use --distrato-documentado NOME|VALOR|AAAA-MM-DD|ARQUIVO.pdf.'
        )
    nome, valor_texto, data_texto, caminho_texto = partes
    valor_decimal = decimal_value(valor_texto)
    if not valor_decimal or valor_decimal <= 0:
        raise CommandError(f'Valor de distrato invalido: {valor_texto}.')
    try:
        data_pagamento = datetime.strptime(data_texto, '%Y-%m-%d').date()
    except ValueError as exc:
        raise CommandError('Data de pagamento invalida. Use AAAA-MM-DD.') from exc
    caminho = Path(caminho_texto).resolve()
    if not caminho.is_file():
        raise CommandError(f'Documento de distrato nao encontrado: {caminho}')
    return nome.strip(), valor_decimal, data_pagamento, caminho


class Command(BaseCommand):
    help = (
        'Concilia colaboradores ativos e desligados e importa somente as '
        'folhas finais selecionadas do acervo Grupo Premium.'
    )

    def add_arguments(self, parser):
        parser.add_argument('raiz')
        parser.add_argument('--arquivo-atual')
        parser.add_argument('--competencia-atual')
        parser.add_argument(
            '--folha-historica',
            action='append',
            default=[],
            help='Pode ser repetido. Formato: AAAA-MM=caminho.xlsx.',
        )
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--reprocessar-atual', action='store_true')
        parser.add_argument('--gerar-pagamentos', action='store_true')
        parser.add_argument(
            '--desligamento-confirmado',
            action='append',
            default=[],
            help=(
                'Correcao comprovada por documento. Pode ser repetido. '
                'Formato: NOME=AAAA-MM-DD.'
            ),
        )
        parser.add_argument(
            '--distrato-documentado',
            action='append',
            default=[],
            help='Pode ser repetido. Formato: NOME|VALOR|AAAA-MM-DD|ARQUIVO.pdf.',
        )
        parser.add_argument('--relatorio')

    def handle(self, *args, **options):
        raiz = Path(options['raiz']).resolve()
        if not raiz.is_dir():
            raise CommandError(f'Pasta não encontrada: {raiz}')
        atual = (
            Path(options['arquivo_atual']).resolve()
            if options['arquivo_atual']
            else localizar_folha_atual(raiz)
        )
        if not atual.is_file():
            raise CommandError(f'Folha atual não encontrada: {atual}')
        if options['competencia_atual']:
            try:
                competencia_atual = datetime.strptime(
                    options['competencia_atual'], '%Y-%m'
                ).date()
            except ValueError as exc:
                raise CommandError('Competência atual inválida. Use AAAA-MM.') from exc
        else:
            competencia_atual = inferir_competencia(atual)

        historicas = [
            _parse_folha_historica(valor)
            for valor in options['folha_historica']
        ]
        desligamentos_confirmados = dict(
            _parse_desligamento_confirmado(valor)
            for valor in options['desligamento_confirmado']
        )
        distratos_documentados = [
            _parse_distrato_documentado(valor)
            for valor in options['distrato_documentado']
        ]
        aplicar = options['aplicar']
        relatorio = {
            'modo': 'aplicar' if aplicar else 'simulacao',
            'raiz': str(raiz),
            'folha_atual': str(atual),
            'competencia_atual': competencia_atual.isoformat(),
            'desligamentos_confirmados': {
                nome: data.isoformat()
                for nome, data in desligamentos_confirmados.items()
            },
            'colaboradores': sincronizar_colaboradores_xlsx(
                content=atual.read_bytes(),
                dry_run=not aplicar,
                desligamentos_confirmados=desligamentos_confirmados,
            ),
            'folhas': [],
            'distratos_documentados': [],
        }
        self.stdout.write(json.dumps(
            relatorio['colaboradores'], ensure_ascii=False, indent=2, default=str
        ))

        if aplicar:
            for nome, valor, data_pagamento, caminho in distratos_documentados:
                relatorio['distratos_documentados'].append(
                    registrar_distrato_documentado(
                        nome=nome,
                        valor=valor,
                        data_pagamento=data_pagamento,
                        caminho=caminho,
                    )
                )
            if options['reprocessar_atual']:
                import hashlib
                digest = hashlib.sha256(atual.read_bytes()).hexdigest()
                existentes = list(FolhaFiscal.objects.filter(hash_origem=digest))
                if existentes:
                    removidos = 0
                    for existente in existentes:
                        prefixo = f'fiscal:{existente.pk}:'
                        pagamentos = PagamentoColaborador.objects.filter(
                            identificador_transacao__startswith=prefixo
                        )
                        removidos += pagamentos.count()
                        pagamentos.delete()
                        existente.delete()
                    relatorio['folha_atual_reprocessada'] = {
                        'pagamentos_substituidos': removidos,
                        'folhas_substituidas': len(existentes),
                    }

            folha, criada = importar_folha_xlsx(
                content=atual.read_bytes(),
                filename=atual.name,
                competencia=competencia_atual,
            )
            resultado = {
                'competencia': competencia_atual.isoformat(),
                'arquivo': str(atual),
                'criada': criada,
                'id': folha.pk,
                'itens': folha.itens.count(),
                'beneficios': folha.beneficios.count(),
                'status': folha.status,
            }
            if options['gerar_pagamentos']:
                gerados, ignorados = gerar_pagamentos_fiscais(folha)
                resultado.update({
                    'pagamentos_gerados': gerados,
                    'pagamentos_ignorados': ignorados,
                })
            relatorio['folhas'].append(resultado)

            for competencia, caminho in historicas:
                folha, criada = importar_folha_xlsx(
                    content=caminho.read_bytes(),
                    filename=caminho.name,
                    competencia=competencia,
                    include_rescisoes=False,
                )
                relatorio['folhas'].append({
                    'competencia': competencia.isoformat(),
                    'arquivo': str(caminho),
                    'criada': criada,
                    'id': folha.pk,
                    'itens': folha.itens.count(),
                    'beneficios': folha.beneficios.count(),
                    'status': folha.status,
                    'pagamentos_gerados': 0,
                })

        if options['relatorio']:
            destino = Path(options['relatorio']).resolve()
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(
                json.dumps(relatorio, ensure_ascii=False, indent=2, default=str),
                encoding='utf-8',
            )
            self.stdout.write(f'Relatório salvo em {destino}')
        self.stdout.write(json.dumps(
            relatorio, ensure_ascii=False, indent=2, default=str
        ))
