from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Max, Sum
from django.http import HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

from core.access import access_required, user_has_access

from .models import Colaborador, PagamentoColaborador
from .programacao_vt import linhas_semana, salvar_decisao, resumo_semana


class DecisaoVTForm(forms.Form):
    pessoa_id = forms.IntegerField(min_value=1)
    segunda = forms.DateField()
    decisao = forms.ChoiceField(choices=[('pagar', 'Pagar benefício'), ('nao', 'Não precisa')])
    valor = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2, localize=True)

    def clean(self):
        dados = super().clean()
        if dados.get('decisao') == 'pagar' and (dados.get('valor') is None or dados['valor'] <= 0):
            self.add_error('valor', 'Informe um valor de benefício maior que zero.')
        return dados


@login_required
@access_required(permission='admissional.view_pagamentocolaborador', profiles=('rh', 'financeiro', 'gestor'))
@require_http_methods(['GET', 'POST'])
def programacao_vt(request):
    pode_editar = all(
        user_has_access(request.user, permission=permissao, profiles=('rh', 'financeiro', 'gestor'))
        for permissao in ('admissional.add_pagamentocolaborador', 'admissional.change_pagamentocolaborador')
    )
    hoje = timezone.localdate()
    try:
        segunda = parse_date(request.POST.get('segunda', '') if request.method == 'POST' else request.GET.get('segunda', ''))
    except ValueError:
        return HttpResponseBadRequest('Data inválida.')
    if segunda is None:
        if request.method == 'POST' or request.GET.get('segunda'):
            return HttpResponseBadRequest('Data inválida.')
        segunda = hoje + timedelta(days=(-hoje.weekday()) % 7)
    if segunda.weekday() != 0 or not 1901 <= segunda.year <= 2099:
        return HttpResponseBadRequest('Selecione uma segunda-feira entre 1901 e 2099.')
    erro = ''
    if request.method == 'POST':
        if not pode_editar:
            raise PermissionDenied
        formulario = DecisaoVTForm(request.POST)
        if formulario.is_valid():
            try:
                salvar_decisao(
                    pessoa_id=formulario.cleaned_data['pessoa_id'], segunda=segunda,
                    pagar=formulario.cleaned_data['decisao'] == 'pagar',
                    valor=formulario.cleaned_data['valor'], usuario=request.user,
                )
            except ValidationError as exc:
                erro = ' '.join(exc.messages)
            except IntegrityError:
                erro = 'Este benefício foi alterado durante a revisão. Atualize a página e confira o lançamento.'
            else:
                messages.success(request, 'Decisão salva para esta segunda-feira.')
                if request.POST.get('voltar_folha') == '1':
                    enviados = QueryDict(request.POST.get('filtros_folha', ''))
                    filtros = QueryDict('', mutable=True)
                    for campo in ('data_inicio', 'data_fim', 'q', 'tipo', 'status', 'categoria', 'unidade', 'colaborador'):
                        if campo in enviados:
                            filtros[campo] = enviados[campo]
                    filtros['segunda_vt'] = segunda.isoformat()
                    return redirect(f'{reverse("lista_pagamentos_colaboradores")}?{filtros.urlencode()}')
                return redirect(f'{reverse("programacao_vt")}?segunda={segunda.isoformat()}')
        else:
            erro = ' '.join(str(e) for erros in formulario.errors.values() for e in erros)
    linhas = linhas_semana(segunda)
    if erro:
        for linha in linhas:
            if str(linha['pessoa'].pk) == request.POST.get('pessoa_id'):
                linha['erro_edicao'] = erro
                linha['decisao'] = request.POST.get('decisao', '')
                linha['valor'] = request.POST.get('valor', '').replace(',', '.')
    return render(request, 'admissional/programacao_vt.html', {
        'segunda': segunda, 'anterior': segunda - timedelta(days=7),
        'proxima': segunda + timedelta(days=7), 'fim_anterior': segunda - timedelta(days=1),
        'linhas': linhas, 'pode_editar': pode_editar, 'erro': erro,
        'total_revisar': sum(l['situacao'] == 'revisar' for l in linhas),
        'total_pagar': sum(l['situacao'] == 'pagar' for l in linhas),
        'resumo_vt': resumo_semana(linhas),
    }, status=400 if erro else 200)


@login_required
@access_required(
    permission='admissional.view_pagamentocolaborador',
    profiles=('rh', 'financeiro', 'gestor'),
)
def historico_vt_colaborador(request, pk):
    colaborador = get_object_or_404(Colaborador, pk=pk)
    pagamentos = (
        PagamentoColaborador.objects.filter(
            colaborador=colaborador,
            tipo='vale_transporte',
            status='pago',
        )
        .prefetch_related('arquivos_importados')
        .order_by('-data_pagamento', '-competencia', '-pk')
    )
    resumo = pagamentos.aggregate(
        total_pago=Sum('valor'),
        ultimo_pagamento=Max('data_pagamento'),
    )
    return render(request, 'admissional/historico_vt_colaborador.html', {
        'colaborador': colaborador,
        'pagamentos': pagamentos,
        'total_pago': resumo['total_pago'] or 0,
        'ultimo_pagamento': resumo['ultimo_pagamento'],
        'quantidade_pagamentos': pagamentos.count(),
        'can_add_pagamento': user_has_access(
            request.user,
            permission='admissional.add_pagamentocolaborador',
            profiles=('rh', 'financeiro', 'gestor'),
        ),
    })
