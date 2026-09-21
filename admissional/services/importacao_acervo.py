from dataclasses import dataclass, field
from difflib import SequenceMatcher
import hashlib
import mimetypes
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from admissional.models import (
    Colaborador,
    PagamentoColaborador,
    cancelar_pagamentos_futuros,
)
from core.models import ArquivoImportado, OrigemArquivoImportado
from fiscal.services import (
    XlsxReader,
    _header_map,
    _valid_name,
    _value,
    decimal_value,
    excel_date,
    normalizar_documento,
    normalizar_texto,
)


ABAS_ATIVAS = {
    'ATIVOS',
    'CLT',
    'PJ',
    'FREELANCE FIXO',
    'SUPERVISOR',
    'ADM',
}
ABA_DESLIGADOS = 'RESCISAO'


@dataclass
class RegistroColaborador:
    nome: str
    documento: str | None
    tipo_contrato: str
    categoria_trabalho: str
    cargo: str = ''
    unidade: str = ''
    contrato: str = ''
    email: str = ''
    salario: object = None
    data_admissao: object = None
    data_desligamento: object = None
    status: str = 'ativo'
    aba: str = ''
    linha: int = 0
    problemas: list[str] = field(default_factory=list)

    @property
    def origem(self):
        return f'{self.aba}:{self.linha}'


def documento_cadastro(valor):
    texto = str(valor or '').strip()
    if not texto or any(char.isalpha() for char in texto):
        return None
    digitos = normalizar_documento(texto)
    if not digitos:
        return None
    if len(digitos) <= 11:
        return digitos.zfill(11)
    if len(digitos) <= 14:
        return digitos.zfill(14)
    return None


def _tipo_contrato(aba, cells, headers):
    if aba == 'CLT':
        return 'clt'
    if aba in {'PJ', 'FREELANCE FIXO', 'SUPERVISOR', 'ADM'}:
        return 'pj'
    indicador = normalizar_texto(_value(cells, headers, 'CLT'))
    return 'clt' if indicador in {'SIM', 'CLT'} else 'pj'


def _registro(aba, linha, cells, headers):
    nome = str(_value(cells, headers, 'COLABORADOR', 'NOME')).strip()
    documento = documento_cadastro(_value(cells, headers, 'CPF', 'CNPJ'))
    tipo_contrato = _tipo_contrato(aba, cells, headers)
    salario = decimal_value(_value(cells, headers, 'SALARIO', 'DIARIA/SALARIO'))
    categoria = 'freelancer' if aba == 'FREELANCE FIXO' else 'fixo'
    if categoria == 'fixo' and salario and 0 < salario < 150 and aba != ABA_DESLIGADOS:
        categoria = 'freelancer'
    admissao_fonte = _value(
        cells,
        headers,
        'ADMISSAO',
        'DATA INICIO',
        'INICIO DE PRESTACAO DE SERVICO',
    )
    desligamento_fonte = _value(
        cells,
        headers,
        'TERMINO DA PRESTACAO',
        'DESLIGAMENTO',
    )
    data_admissao = excel_date(admissao_fonte)
    data_desligamento = excel_date(desligamento_fonte)
    problemas = []
    admissao_informada = normalizar_texto(admissao_fonte) not in {'', '-', '/', 'N/A', 'NA'}
    desligamento_informado = (
        normalizar_texto(desligamento_fonte) not in {'', '-', '/', 'N/A', 'NA'}
    )
    if admissao_informada and not data_admissao:
        problemas.append(f'Data de admissao invalida em {aba}:{linha}: {admissao_fonte}.')
    if desligamento_informado and not data_desligamento:
        problemas.append(
            f'Data de desligamento invalida em {aba}:{linha}: {desligamento_fonte}.'
        )
    if data_admissao and data_desligamento and data_desligamento < data_admissao:
        problemas.append(
            f'Data de desligamento anterior à admissão em {aba}:{linha}.'
        )
        data_admissao = None
    return RegistroColaborador(
        nome=nome,
        documento=documento,
        tipo_contrato=tipo_contrato,
        categoria_trabalho=categoria,
        cargo=str(_value(cells, headers, 'CARGO')).strip(),
        unidade=str(_value(cells, headers, 'UNIDADE', 'BASE')).strip(),
        contrato=str(_value(cells, headers, 'CONTRATO')).strip(),
        email=str(_value(cells, headers, 'E-MAIL', 'EMAIL')).strip(),
        salario=salario,
        data_admissao=data_admissao,
        data_desligamento=data_desligamento,
        status='desligado' if aba == ABA_DESLIGADOS else 'ativo',
        aba=aba,
        linha=linha,
        problemas=problemas,
    )


def _nomes_compativeis(nome_a, nome_b):
    a = normalizar_texto(nome_a)
    b = normalizar_texto(nome_b)
    if a == b:
        return True
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    cobertura = len(tokens_a & tokens_b) / max(1, min(len(tokens_a), len(tokens_b)))
    return cobertura >= .72 or SequenceMatcher(None, a, b).ratio() >= .78


def coletar_registros_colaboradores(content):
    reader = XlsxReader(content)
    registros = []
    problemas = []
    for nome_aba in reader.sheets:
        aba = normalizar_texto(nome_aba)
        if aba not in ABAS_ATIVAS | {ABA_DESLIGADOS}:
            continue
        rows = reader.rows(nome_aba)
        header_row, headers = _header_map(rows)
        if not header_row:
            problemas.append(f'Cabeçalho não encontrado na aba {nome_aba}.')
            continue
        for linha, cells in rows:
            if linha <= header_row:
                continue
            nome = _value(cells, headers, 'COLABORADOR', 'NOME')
            if not _valid_name(nome):
                continue
            registros.append(_registro(aba, linha, cells, headers))

    # Uma pessoa pode continuar na aba mensal porque recebeu dias trabalhados e,
    # ao mesmo tempo, constar em RESCISAO. Nesse caso o desligamento prevalece.
    # A aba ativa so prevalece quando a admissao e posterior ao desligamento,
    # caracterizando uma readmissao.
    consolidados = {}
    documento_para_chave = {}
    for registro in sorted(registros, key=lambda item: item.status == 'ativo'):
        chave_nome = f'nome:{normalizar_texto(registro.nome)}'
        chave = f'doc:{registro.documento}' if registro.documento else chave_nome
        if registro.documento and registro.documento in documento_para_chave:
            chave_existente = documento_para_chave[registro.documento]
            anterior = consolidados[chave_existente]
            if not _nomes_compativeis(anterior.nome, registro.nome):
                registro.problemas.append(
                    f'Documento {registro.documento} também aparece para '
                    f'{anterior.nome} ({anterior.origem}).'
                )
                problemas.extend(registro.problemas)
                registro.documento = None
                chave = chave_nome
            else:
                chave = chave_existente
        if chave in consolidados:
            anterior = consolidados[chave]
            ativo = registro if registro.status == 'ativo' else anterior
            desligado = registro if registro.status == 'desligado' else anterior
            estados_diferentes = registro.status != anterior.status
            readmitido = (
                estados_diferentes
                and ativo.data_admissao
                and desligado.data_desligamento
                and ativo.data_admissao > desligado.data_desligamento
            )
            if estados_diferentes:
                escolhido = ativo if readmitido or not desligado.data_desligamento else desligado
            elif registro.status == 'desligado':
                candidatos = [
                    item for item in (anterior, registro) if item.data_desligamento
                ]
                escolhido = (
                    max(candidatos, key=lambda item: item.data_desligamento)
                    if candidatos else registro
                )
            else:
                escolhido = registro

            complemento = anterior if escolhido is registro else registro
            escolhido.data_admissao = escolhido.data_admissao or complemento.data_admissao
            escolhido.cargo = escolhido.cargo or complemento.cargo
            escolhido.unidade = escolhido.unidade or complemento.unidade
            escolhido.contrato = escolhido.contrato or complemento.contrato
            escolhido.email = escolhido.email or complemento.email
            escolhido.salario = escolhido.salario or complemento.salario
            if escolhido.status == 'ativo':
                escolhido.data_desligamento = None
            else:
                escolhido.data_desligamento = (
                    escolhido.data_desligamento or complemento.data_desligamento
                )
            escolhido.problemas = [*anterior.problemas, *registro.problemas]
            consolidados[chave] = escolhido
        else:
            consolidados[chave] = registro
        if registro.documento:
            documento_para_chave[registro.documento] = chave
        problemas.extend(registro.problemas)
    return list(consolidados.values()), list(dict.fromkeys(problemas))


def _indice_colaboradores():
    por_documento = {}
    por_nome = {}
    for colaborador in Colaborador.objects.all():
        documento = normalizar_documento(colaborador.cpf)
        if documento:
            por_documento.setdefault(documento, []).append(colaborador)
        por_nome[normalizar_texto(colaborador.nome)] = colaborador
    return por_documento, por_nome


@transaction.atomic
def sincronizar_colaboradores_xlsx(
    *, content, dry_run=False, desligamentos_confirmados=None
):
    registros, problemas = coletar_registros_colaboradores(content)
    desligamentos_confirmados = desligamentos_confirmados or {}
    por_nome_fonte = {
        normalizar_texto(registro.nome): registro for registro in registros
    }
    for nome, data_desligamento in desligamentos_confirmados.items():
        registro = por_nome_fonte.get(normalizar_texto(nome))
        if not registro:
            problemas.append(
                f'Desligamento documental sem correspondente na folha: {nome}.'
            )
            continue
        registro.status = 'desligado'
        registro.data_desligamento = data_desligamento

    por_documento, por_nome = _indice_colaboradores()
    contadores = {
        'registros_fonte': len(registros),
        'criados': 0,
        'atualizados': 0,
        'sem_alteracao': 0,
        'ativos': 0,
        'desligados': 0,
        'conflitos': len(problemas),
        'problemas': problemas,
    }
    novos = []
    atualizados = []
    campos_atualizados = set()
    desativados = []
    for registro in registros:
        colaborador = None
        documento_duplicado = False
        if registro.documento:
            candidatos_documento = por_documento.get(registro.documento, [])
            documento_duplicado = len(candidatos_documento) > 1
            if candidatos_documento:
                exatos = [
                    item for item in candidatos_documento
                    if normalizar_texto(item.nome) == normalizar_texto(registro.nome)
                ]
                colaborador = exatos[0] if len(exatos) == 1 else candidatos_documento[0]
            if documento_duplicado:
                contadores['conflitos'] += 1
                contadores['problemas'].append(
                    f'{registro.origem}: documento {registro.documento} ja esta '
                    f'em {len(candidatos_documento)} cadastros; usado cadastro '
                    f'#{colaborador.pk} ({colaborador.nome}).'
                )
        colaborador = colaborador or por_nome.get(normalizar_texto(registro.nome))
        criado = colaborador is None
        if criado:
            colaborador = Colaborador()

        valores = {
            'nome': registro.nome[:200],
            'tipo_contrato': registro.tipo_contrato,
            'categoria_trabalho': registro.categoria_trabalho,
            'cargo': registro.cargo[:200],
            'setor': 'Operacional' if registro.cargo else colaborador.setor,
            'unidade': registro.unidade[:100],
            'contrato': registro.contrato[:200],
            'email': registro.email[:254],
            'data_admissao': registro.data_admissao,
            'data_desligamento': registro.data_desligamento,
            'status': registro.status,
        }
        if registro.documento and not documento_duplicado:
            valores['cpf'] = registro.documento
        if registro.salario is not None:
            valores['salario'] = registro.salario

        alterados = []
        for campo, valor in valores.items():
            if valor in ('', None) and not (
                campo == 'data_desligamento' and registro.status == 'ativo'
            ):
                continue
            if getattr(colaborador, campo, None) != valor:
                setattr(colaborador, campo, valor)
                alterados.append(campo)

        try:
            colaborador.clean()
        except ValidationError as exc:
            contadores['conflitos'] += 1
            contadores['problemas'].append(
                f'{registro.origem}: conflito ao salvar {registro.nome}: {exc}'
            )
            continue
        contadores[registro.status + 's'] += 1
        if criado:
            contadores['criados'] += 1
            novos.append(colaborador)
        elif alterados:
            contadores['atualizados'] += 1
            atualizados.append(colaborador)
            campos_atualizados.update(alterados)
            if 'status' in alterados and registro.status in Colaborador.STATUS_SEM_PAGAMENTO:
                desativados.append(colaborador.pk)
        else:
            contadores['sem_alteracao'] += 1

        if dry_run:
            continue
        if registro.documento:
            por_documento.setdefault(registro.documento, []).append(colaborador)
        por_nome[normalizar_texto(registro.nome)] = colaborador

    if dry_run:
        transaction.set_rollback(True)
    else:
        try:
            if novos:
                Colaborador.objects.bulk_create(novos, batch_size=200)
            if atualizados and campos_atualizados:
                Colaborador.objects.bulk_update(
                    atualizados,
                    sorted(campos_atualizados),
                    batch_size=200,
                )
            if desativados:
                cancelar_pagamentos_futuros(desativados)
        except IntegrityError as exc:
            raise ValidationError(
                f'Conflito de integridade durante a gravacao em lote: {exc}'
            ) from exc
    return contadores


def localizar_folha_atual(raiz):
    raiz = Path(raiz)
    candidatos = []
    for caminho in raiz.rglob('*.xlsx'):
        if caminho.name.startswith('~$'):
            continue
        nome = normalizar_texto(caminho.name)
        if 'PLANILHA DE PAGAMENTO' not in nome:
            continue
        try:
            reader = XlsxReader(caminho.read_bytes())
        except Exception:
            continue
        abas = {normalizar_texto(aba) for aba in reader.sheets}
        if not abas.intersection({'ATIVOS', 'CLT', 'PJ'}):
            continue
        versoes = [
            int(valor)
            for valor in __import__('re').findall(r'VERSAO\s*0*(\d+)', nome)
        ]
        candidatos.append((caminho.stat().st_mtime, max(versoes, default=0), caminho))
    if not candidatos:
        raise FileNotFoundError('Nenhuma folha de pagamento com cadastro ativo foi encontrada.')
    # A data de alteração é a melhor indicação para a folha corrente; a versão
    # desempata cópias salvas no mesmo período.
    return max(candidatos, key=lambda item: (item[0], item[1]))[2]


@transaction.atomic
def registrar_distrato_documentado(
    *, nome, valor, data_pagamento, caminho, dry_run=False
):
    caminho = Path(caminho).resolve()
    if not caminho.is_file():
        raise FileNotFoundError(f'Comprovante de distrato nao encontrado: {caminho}')
    colaboradores = [
        item for item in Colaborador.objects.all()
        if normalizar_texto(item.nome) == normalizar_texto(nome)
    ]
    if len(colaboradores) != 1:
        raise ValidationError(
            f'Esperado um colaborador para {nome}; encontrados {len(colaboradores)}.'
        )
    colaborador = colaboradores[0]
    existente = PagamentoColaborador.objects.filter(
        colaborador=colaborador,
        tipo='distrato',
        valor=valor,
        status='pago',
        data_pagamento=data_pagamento,
    ).first()
    if dry_run:
        return {'nome': nome, 'acao': 'existente' if existente else 'criar'}

    conteudo = caminho.read_bytes()
    digest = hashlib.sha256(conteudo).hexdigest()
    pagamento = existente or PagamentoColaborador(
        colaborador=colaborador,
        tipo='distrato',
        competencia=data_pagamento.replace(day=1),
        competencia_fim=data_pagamento,
        valor=valor,
        data_vencimento=data_pagamento,
        status='pago',
        data_pagamento=data_pagamento,
        observacao=f'Distrato confirmado pelo documento {caminho.name}.',
        identificador_transacao=f'acervo:distrato:{digest[:32]}',
    )
    if not existente:
        pagamento.full_clean()
        pagamento.save()

    arquivo, criado = ArquivoImportado.objects.get_or_create(
        sha256=digest,
        defaults={
            'categoria': 'pagamento_colaborador',
            'subcategoria': 'distrato',
            'area': 'rh',
            'nome_original': caminho.name[:255],
            'tamanho': len(conteudo),
            'mime_type': mimetypes.guess_type(caminho.name)[0] or 'application/pdf',
            'status': 'vinculado',
            'metadados': {
                'colaborador': colaborador.nome,
                'data_pagamento': data_pagamento.isoformat(),
                'valor': str(valor),
            },
        },
    )
    if criado:
        arquivo.arquivo.save(caminho.name, ContentFile(conteudo), save=False)
    if not arquivo.object_id:
        arquivo.content_object = pagamento
        arquivo.status = 'vinculado'
    arquivo.save()
    OrigemArquivoImportado.objects.get_or_create(
        caminho_relativo=str(caminho)[:2000],
        defaults={
            'arquivo_importado': arquivo,
            'pasta_raiz': caminho.anchor[:255],
        },
    )
    return {
        'nome': colaborador.nome,
        'acao': 'existente' if existente else 'criado',
        'pagamento_id': pagamento.pk,
        'arquivo_id': arquivo.pk,
    }
