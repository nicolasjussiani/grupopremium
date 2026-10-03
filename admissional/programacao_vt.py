"""Calendário de revisão do VT, independente da baixa da semana anterior."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .calculo_folha import calcular_vt_antecipado
from .models import Colaborador, PagamentoColaborador, PresencaDiaria, ProgramacaoVT


def segundas_no_periodo(inicio, fim):
    dia = inicio + timedelta(days=(-inicio.weekday()) % 7)
    while dia <= fim:
        yield dia
        dia += timedelta(days=7)


def equipe_vt(segunda):
    return Colaborador.objects.filter(tipo_contrato__in=('clt', 'pj')).exclude(
        status__in=Colaborador.STATUS_SEM_PAGAMENTO,
    ).filter(Q(data_admissao__isnull=True) | Q(data_admissao__lte=segunda + timedelta(days=6))).order_by('nome', 'pk')


def tipo_beneficio(colaborador):
    return 'vale_transporte' if colaborador.tipo_contrato == 'clt' else 'ajuda_custo'


def valor_proporcional(valor_semana, dias_presentes):
    """Arredonda apenas o total, sem arredondar a diária intermediária."""
    return (valor_semana * Decimal(dias_presentes) / Decimal(7)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )


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
    bases_anteriores = {}
    for decisao_anterior in ProgramacaoVT.objects.filter(
        colaborador_id__in=ids, segunda__lt=segunda, valor_semana_completa__isnull=False,
    ).order_by('colaborador_id', '-segunda'):
        bases_anteriores.setdefault(decisao_anterior.colaborador_id, decisao_anterior.valor_semana_completa)
    pagamentos = {}
    for p in PagamentoColaborador.objects.filter(
        colaborador_id__in=ids, tipo__in=('vale_transporte', 'ajuda_custo'), data_vencimento=segunda,
    ).order_by('pk'):
        chave = (p.colaborador_id, p.tipo)
        if chave not in pagamentos or p.status != 'cancelado':
            pagamentos[chave] = p
    anteriores = {d.colaborador_id: d for d in ProgramacaoVT.objects.filter(
        colaborador_id__in=ids, segunda=segunda - timedelta(days=7), antecipado=True)}
    pagos_anteriores = set(PagamentoColaborador.objects.filter(
        colaborador_id__in=ids, tipo__in=('vale_transporte', 'ajuda_custo'),
        data_vencimento=segunda - timedelta(days=7), status='pago',
    ).values_list('colaborador_id', flat=True))
    jornadas = {}
    for d in ProgramacaoVT.objects.filter(colaborador_id__in=ids, segunda__lt=segunda,
        antecipado=True).order_by('colaborador_id', '-segunda'):
        jornadas.setdefault(d.colaborador_id, d.dias_jornada)
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
        valor_base = (
            decisao.valor_semana_completa if decisao and decisao.valor_semana_completa is not None
            else bases_anteriores.get(pessoa.pk, getattr(pessoa, f'{beneficio}_semanal'))
        )
        total_calculado = valor_proporcional(valor_base, len(presenca['datas'])) if valor_base else None
        dias_semana = []
        for indice, nome in enumerate(('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom')):
            dia = segunda - timedelta(days=7 - indice)
            status = presenca['por_dia'].get(dia, 'indefinido')
            dias_semana.append({
                'data': dia, 'nome': nome, 'status': status,
                'descricao': dict(PresencaDiaria.STATUS_CHOICES).get(status, 'Não definido'),
            })
        anterior = anteriores.get(pessoa.pk)
        salvo = decisao if decisao and decisao.antecipado else None
        jornada = salvo.dias_jornada if salvo else jornadas.get(pessoa.pk)
        previstos = salvo.dias_previstos if salvo else jornada
        if not salvo and jornada and pessoa.data_admissao and pessoa.data_admissao > segunda:
            previstos = sum(segunda + timedelta(days=i) >= pessoa.data_admissao for i in range(jornada))
        datas_faltas = [dia for dia, st in presenca['por_dia'].items() if st == 'falta']
        faltas = salvo.faltas_descontar if salvo else (len(datas_faltas) if anterior and pessoa.pk in pagos_anteriores else 0)
        diaria = salvo.diaria_desconto if salvo else (
            anterior.valor_semana_completa / Decimal(anterior.dias_jornada)
            if anterior and anterior.dias_jornada and anterior.valor_semana_completa else None)
        if diaria is not None:
            diaria = diaria.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        desconto = salvo.desconto_adicional if salvo else Decimal('0')
        total_antecipado = None
        if valor_base and jornada and previstos is not None:
            try:
                total_antecipado = calcular_vt_antecipado(valor_base, jornada, previstos, faltas, diaria, desconto)
            except ValidationError:
                pass
        linhas.append({
            'dias_jornada': jornada, 'dias_previstos': previstos, 'faltas_descontar': faltas,
            'diaria_desconto': diaria, 'desconto_adicional': desconto,
            'datas_faltas': datas_faltas, 'valor_antecipado': total_antecipado,

            'pessoa': pessoa, 'pagamento': pagamento, 'situacao': situacao,
            'valor': valor_base,
            'valor_calculado': total_calculado,
            'dias_pendentes': 7 - presenca['definidos'],
            'calculo_salvo': decisao if decisao and decisao.valor_semana_completa is not None else None,
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
def salvar_decisao(*, pessoa_id, segunda, pagar, valor, usuario, antecipado=False, dias_jornada=None, dias_previstos=None, faltas_descontar=0, diaria_desconto=None, desconto_adicional=Decimal("0")):
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
        if valor is None or not valor.is_finite() or valor <= 0:
            raise ValidationError('Informe o valor da semana completa maior que zero.')
        presenca = presencas_por_pessoa([pessoa.pk], segunda - timedelta(days=7), segunda - timedelta(days=1))
        dias_presentes = len(presenca.get(pessoa.pk, {'datas': []})['datas'])
        if antecipado:
            if dias_jornada is None or dias_previstos is None:
                raise ValidationError('Informe a jornada e os dias previstos para a semana que será paga.')
            total = calcular_vt_antecipado(valor, dias_jornada, dias_previstos, faltas_descontar, diaria_desconto, desconto_adicional)
        else:
            total = valor_proporcional(valor, dias_presentes)
        if total <= 0:
            raise ValidationError('O valor calculado é R$ 0,00. Confira as presenças ou selecione Não precisa.')
        pagamento = pagamentos[0] if pagamentos else PagamentoColaborador(
            colaborador=pessoa, tipo=beneficio, competencia=segunda,
            data_vencimento=segunda, status='pendente', criado_por=usuario,
            observacao='Selecionado na programação semanal de VT e ajuda de custo.',
        )
        pagamento.valor = total
        pagamento.full_clean()
        pagamento.save()
    else:
        for pagamento in pagamentos:
            pagamento.status = 'cancelado'
            pagamento.save(update_fields=['status', 'atualizado_em'])
    ProgramacaoVT.objects.update_or_create(
        colaborador=pessoa, segunda=segunda,
        defaults={
            'pagar': pagar, 'atualizado_por': usuario,
            **({'valor_semana_completa': valor, 'dias_presentes': dias_presentes,
                'antecipado': antecipado, 'dias_jornada': dias_jornada if antecipado else None,
                'dias_previstos': dias_previstos if antecipado else None,
                'faltas_descontar': faltas_descontar if antecipado else 0,
                'diaria_desconto': diaria_desconto if antecipado else None,
                'desconto_adicional': desconto_adicional if antecipado else Decimal('0'),
            } if pagar else {}),
        },
    )
