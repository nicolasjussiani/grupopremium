"""Calendário de revisão do VT, independente da baixa da semana anterior."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import Colaborador, PagamentoColaborador, PresencaDiaria, ProgramacaoVT


def segundas_no_periodo(inicio, fim):
    dia = inicio + timedelta(days=(-inicio.weekday()) % 7)
    while dia <= fim:
        yield dia
        dia += timedelta(days=7)


def equipe_vt(segunda):
    return Colaborador.objects.filter(tipo_contrato__in=('clt', 'pj')).exclude(
        status__in=Colaborador.STATUS_SEM_PAGAMENTO,
    ).filter(Q(data_admissao__isnull=True) | Q(data_admissao__lte=segunda)).order_by('nome', 'pk')


def tipo_beneficio(colaborador):
    return 'vale_transporte' if colaborador.tipo_contrato == 'clt' else 'ajuda_custo'


def presencas_por_pessoa(ids, inicio, fim):
    resumo = {}
    for pessoa, dia, status in PresencaDiaria.objects.filter(
        colaborador_id__in=ids, data__range=(inicio, fim),
    ).order_by('data').values_list('colaborador_id', 'data', 'status'):
        item = resumo.setdefault(pessoa, {'datas': [], 'definidos': 0, 'por_dia': {}})
        item['por_dia'][dia] = status
        if status != 'indefinido':
            item['definidos'] += 1
        if status == 'presente':
            item['datas'].append(dia)
    return resumo


def linhas_semana(segunda, *, busca='', unidade='', categoria='', colaborador_id=None, tipo=''):
    equipe = equipe_vt(segunda)
    if tipo in ('vale_transporte', 'ajuda_custo'):
        equipe = equipe.filter(tipo_contrato='clt' if tipo == 'vale_transporte' else 'pj')
    if busca:
        equipe = equipe.filter(
            Q(nome__icontains=busca) | Q(cpf__icontains=busca) | Q(unidade__icontains=busca)
        )
    if unidade:
        equipe = equipe.filter(unidade=unidade)
    if categoria:
        equipe = equipe.filter(categoria_trabalho=categoria)
    if colaborador_id:
        equipe = equipe.filter(pk=colaborador_id)
    equipe = list(equipe)
    ids = [p.pk for p in equipe]
    presencas = presencas_por_pessoa(ids, segunda - timedelta(days=7), segunda - timedelta(days=1))
    decisoes = {d.colaborador_id: d for d in ProgramacaoVT.objects.filter(segunda=segunda)}
    pagamentos = {}
    for p in PagamentoColaborador.objects.filter(
        colaborador_id__in=ids, tipo__in=('vale_transporte', 'ajuda_custo'), data_vencimento=segunda,
    ).order_by('pk'):
        chave = (p.colaborador_id, p.tipo)
        if chave not in pagamentos or p.status != 'cancelado':
            pagamentos[chave] = p
    linhas = []
    for pessoa in equipe:
        beneficio = tipo_beneficio(pessoa)
        pagamento = pagamentos.get((pessoa.pk, beneficio))
        decisao = decisoes.get(pessoa.pk)
        situacao = 'revisar'
        if pagamento:
            situacao = {'pago': 'pago', 'pendente': 'pagar', 'cancelado': 'nao'}[pagamento.status]
        elif decisao and not decisao.pagar:
            situacao = 'nao'
        presenca = presencas.get(pessoa.pk, {'datas': [], 'definidos': 0, 'por_dia': {}})
        dias_semana = []
        for indice, nome in enumerate(('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom')):
            dia = segunda - timedelta(days=7 - indice)
            status = presenca['por_dia'].get(dia, 'indefinido')
            dias_semana.append({
                'data': dia, 'nome': nome, 'status': status,
                'descricao': dict(PresencaDiaria.STATUS_CHOICES).get(status, 'Não definido'),
            })
        linhas.append({
            'pessoa': pessoa, 'pagamento': pagamento, 'situacao': situacao,
            'valor': pagamento.valor if pagamento else getattr(pessoa, f'{beneficio}_semanal'),
            'tipo_beneficio': beneficio,
            'nome_beneficio': 'VT' if beneficio == 'vale_transporte' else 'Ajuda de custo',
            'datas': presenca['datas'], 'dias': len(presenca['datas']) if presenca['definidos'] else None,
            'definidos': presenca['definidos'],
            'dias_semana': dias_semana,
            'decisao': situacao if situacao in ('pagar', 'nao') else '',
        })
    return linhas


def resumo_semana(linhas):
    return {
        'total': len(linhas),
        'clt': sum(l['tipo_beneficio'] == 'vale_transporte' for l in linhas),
        'pj': sum(l['tipo_beneficio'] == 'ajuda_custo' for l in linhas),
        'revisar': sum(l['situacao'] == 'revisar' for l in linhas),
        'pagar': sum(l['situacao'] == 'pagar' for l in linhas),
        'nao': sum(l['situacao'] == 'nao' for l in linhas),
        'pago': sum(l['situacao'] == 'pago' for l in linhas),
        'valor_pendente': sum((l['pagamento'].valor for l in linhas if l['situacao'] == 'pagar'), Decimal('0')),
    }


@transaction.atomic
def salvar_decisao(*, pessoa_id, segunda, pagar, valor, usuario):
    if segunda.weekday() != 0:
        raise ValidationError('Selecione uma segunda-feira.')
    # Serializa decisões da mesma pessoa e evita dois lançamentos na semana.
    pessoa = equipe_vt(segunda).select_for_update().filter(pk=pessoa_id).first()
    if pessoa is None:
        raise ValidationError('Colaborador indisponível para benefícios nesta semana.')
    beneficio = tipo_beneficio(pessoa)
    pagamentos = list(PagamentoColaborador.objects.select_for_update().filter(
        colaborador=pessoa, tipo=beneficio, data_vencimento=segunda,
    ).exclude(status='cancelado'))
    if any(p.status == 'pago' for p in pagamentos):
        raise ValidationError('Benefício já pago. O histórico não pode ser alterado pela programação.')
    if pagar:
        pagamento = pagamentos[0] if pagamentos else PagamentoColaborador(
            colaborador=pessoa, tipo=beneficio, competencia=segunda,
            data_vencimento=segunda, status='pendente', criado_por=usuario,
            observacao='Selecionado na programação semanal de VT e ajuda de custo.',
        )
        pagamento.valor = valor
        pagamento.full_clean()
        pagamento.save()
    else:
        for pagamento in pagamentos:
            pagamento.status = 'cancelado'
            pagamento.save(update_fields=['status', 'atualizado_em'])
    ProgramacaoVT.objects.update_or_create(
        colaborador=pessoa, segunda=segunda,
        defaults={'pagar': pagar, 'atualizado_por': usuario},
    )
