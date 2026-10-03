from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.access import access_required, user_has_access
from .forms import PagamentoColaboradorForm
from .models import Colaborador, PagamentoColaborador, PresencaDiaria


@login_required
@access_required(permission='admissional.view_pagamentocolaborador', profiles=('rh', 'financeiro', 'gestor'))
@require_http_methods(['GET', 'POST'])
def programacao_salarios(request):
    mes = request.POST.get('mes') if request.method == 'POST' else request.GET.get('mes', timezone.localdate().strftime('%Y-%m'))
    try:
        inicio = date.fromisoformat(mes + '-01')
        fim = inicio.replace(day=monthrange(inicio.year, inicio.month)[1])
    except (ValueError, TypeError):
        return HttpResponseBadRequest('Informe o mês da folha.')
    pode_editar = all(user_has_access(request.user, permission=p, profiles=('rh', 'financeiro', 'gestor')) for p in (
        'admissional.add_pagamentocolaborador', 'admissional.change_pagamentocolaborador'))
    erro_form = None
    erro_pessoa = None
    erro = ''
    equipe = Colaborador.objects.exclude(status__in=Colaborador.STATUS_SEM_PAGAMENTO).filter(
        tipo_contrato__in=('clt', 'pj'),
    ).filter(Q(data_admissao__isnull=True) | Q(data_admissao__lte=fim))
    if request.method == 'POST':
        if not pode_editar:
            raise PermissionDenied
        try:
            pessoa_id = int(request.POST.get('pessoa_id', ''))
        except ValueError:
            return HttpResponseBadRequest('Colaborador inválido.')
        try:
            with transaction.atomic():
                pessoa = get_object_or_404(equipe.select_for_update(), pk=pessoa_id)
                pagamento = PagamentoColaborador.objects.select_for_update().filter(
                    colaborador=pessoa, tipo='salario', competencia__range=(inicio, fim),
                ).exclude(status='cancelado').first()
                if pagamento and pagamento.status == 'pago':
                    erro = 'Este salário já foi pago. O cálculo salvo não pode ser alterado.'
                else:
                    dados = request.POST.copy()
                    dados.update({'colaborador': str(pessoa.pk), 'tipo': 'salario',
                        'competencia': inicio.isoformat(), 'competencia_fim': fim.isoformat(),
                        'status': 'pendente', 'valor': '', 'valor_diaria': '',
                        'chave_pix': pagamento.chave_pix if pagamento else '',
                    })
                    form = PagamentoColaboradorForm(dados, instance=pagamento)
                    form.fields['salario_base'].required = True
                    if form.is_valid():
                        salvo = form.save(commit=False)
                        salvo.criado_por = salvo.criado_por or request.user
                        salvo.save()
                        return redirect(reverse('programacao_salarios') + '?mes=' + mes)
                    erro_form, erro_pessoa = form, pessoa.pk
        except IntegrityError:
            erro = 'Já existe um lançamento para esse período. Atualize a página e confira a folha.'
    pagamentos = {p.colaborador_id: p for p in PagamentoColaborador.objects.filter(
        tipo='salario', competencia__range=(inicio, fim),
    ).exclude(status='cancelado')}
    presencas = {}
    for pessoa_id, dia, status in PresencaDiaria.objects.filter(
        colaborador__in=equipe, data__range=(inicio, fim),
    ).order_by('data').values_list('colaborador_id', 'data', 'status'):
        info = presencas.setdefault(pessoa_id, {'presentes': 0, 'faltas': []})
        if status == 'presente':
            info['presentes'] += 1
        elif status == 'falta':
            info['faltas'].append(dia)
    linhas = []
    for pessoa in equipe.order_by('nome', 'pk'):
        pagamento = pagamentos.get(pessoa.pk)
        info = presencas.get(pessoa.pk, {'presentes': 0, 'faltas': []})
        sugestao = min(30, info['presentes'] + len(info['faltas'])) or None
        inicial = {
            'salario_base': (pagamento.salario_base if pagamento and pagamento.salario_base is not None else pessoa.salario),
            'dias_trabalhados': pagamento.dias_trabalhados if pagamento else sugestao,
            'faltas': pagamento.faltas if pagamento else len(info['faltas']),
            'gratificacao': pagamento.gratificacao if pagamento else 0,
            'outros_descontos': pagamento.outros_descontos if pagamento else 0,
            'data_vencimento': pagamento.data_vencimento if pagamento else None,
            'observacao': pagamento.observacao if pagamento else '',
        }
        form = erro_form if erro_pessoa == pessoa.pk else PagamentoColaboradorForm(initial=inicial, prefix=None)
        for name, field in form.fields.items():
            field.widget.attrs['id'] = f'salario-{pessoa.pk}-{name}'
        form.fields['salario_base'].help_text = 'Salário mensal. O cálculo usa divisor 30; este valor pode ser corrigido para o lançamento.'
        form.fields['dias_trabalhados'].label = 'Dias do período (antes das faltas)'
        campos = [form[n] for n in inicial]
        linhas.append({'pessoa': pessoa, 'pagamento': pagamento, 'campos': campos,
            'faltas': info['faltas'], 'presentes': info['presentes'],
            'erros': form.errors if form.is_bound else None})
    return render(request, 'admissional/programacao_salarios.html', {
        'mes': mes, 'linhas': linhas, 'pode_editar': pode_editar, 'erro': erro,
        'total': sum((p.valor for p in pagamentos.values()), Decimal('0')),
    }, status=400 if erro or erro_form else 200)
