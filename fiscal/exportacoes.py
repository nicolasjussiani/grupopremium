from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from core.access import access_required
from core.planilhas import exportar_xlsx
from .models import FolhaFiscal
from .relatorios import dados_folha, graficos_lotes
from .views import ACCESS, _folhas_com_resumo


@login_required
@access_required(permission='fiscal.view_folhafiscal', **ACCESS)
@require_GET
def exportar_lotes(request):
    folhas = list(_folhas_com_resumo())
    colunas = [('Lote', 'numero', 10), ('Competência', 'data', 16), ('Versão', 'numero', 10),
               ('Título', 'texto', 40), ('Situação', 'texto', 24), ('Registros de folha', 'numero', 22),
               ('Beneficiários', 'numero', 18), ('Pendências', 'numero', 16)]
    linhas = [[f.pk, f.competencia, f.versao, f.titulo, f.get_status_display(), f.total_itens,
               f.quantidade_beneficios, f.itens_revisar + f.beneficios_revisar] for f in folhas]
    return exportar_xlsx(
        titulo='Base Fiscal — lotes importados',
        contexto='Todos os lotes, incluindo versões anteriores. Para os valores e colaboradores, exporte o lote desejado na tela de detalhes.',
        abas=[('Lotes', colunas, linhas)], graficos=graficos_lotes(folhas), nome='fiscal-lotes',
    )


@login_required
@access_required(permission='fiscal.view_folhafiscal', **ACCESS)
@require_GET
def exportar_folha(request, pk):
    folha = get_object_or_404(FolhaFiscal, pk=pk)
    dados = dados_folha(folha)
    colunas = [
        ('Cadastro', 'numero', 12), ('Colaborador na origem', 'texto', 40), ('CPF/CNPJ', 'texto', 22),
        ('Unidade', 'texto', 25), ('Regime', 'texto', 22), ('Cargo', 'texto', 24), ('Contrato', 'texto', 24),
        ('Salário base', 'moeda', 18), ('Dias trabalhados', 'numero', 18), ('Valor do dia', 'moeda', 18),
        ('Bonificação', 'moeda', 18), ('Faltas (R$)', 'moeda', 18), ('Descontos', 'moeda', 18),
        ('Valor a executar', 'moeda', 20), ('Valor planejado', 'moeda', 20),
        ('Situação na origem', 'texto', 25), ('Conciliação', 'texto', 18),
        ('Pagamento no sistema', 'texto', 25), ('Valor no sistema', 'moeda', 20),
        ('Data do pagamento', 'data', 20), ('Chave PIX', 'texto', 35), ('Pendências', 'texto', 45),
        ('Observações', 'texto', 45), ('Aba de origem', 'texto', 24), ('Linha de origem', 'numero', 17),
    ]
    linhas = []
    for i in dados['itens']:
        p = i.pagamento
        linhas.append([i.colaborador_id, i.nome_fonte, i.cpf_cnpj_fonte, i.unidade, i.get_regime_display(), i.cargo,
                       i.contrato, i.salario_base, i.dias_trabalhados, i.valor_dia, i.bonificacao, i.faltas,
                       i.descontos, i.valor_executar, i.valor_planejado, i.get_status_fonte_display(),
                       i.get_status_conciliacao_display(), p.get_status_display() if p else 'Não gerado',
                       p.valor if p else None, p.data_pagamento if p else None, i.pix,
                       '; '.join(i.problemas), i.observacoes, i.aba_origem, i.linha_origem])
    col_beneficios = [
        ('Cadastro', 'numero', 12), ('Colaborador na origem', 'texto', 40), ('Benefício', 'texto', 24),
        ('Base', 'texto', 25), ('Contrato', 'texto', 25), ('Semana da origem', 'numero', 20),
        ('Valor da parcela na origem', 'moeda', 27), ('Situação na origem', 'texto', 25),
        ('Conciliação', 'texto', 18), ('Pagamento no sistema', 'texto', 25), ('Valor no sistema', 'moeda', 20),
        ('Vencimento', 'data', 18), ('Data do pagamento', 'data', 20), ('Chave PIX', 'texto', 35),
        ('Pendências', 'texto', 45),
    ]
    beneficios = []
    for b in dados['beneficios']:
        for parcela in list(b.parcelas.all()) or [None]:
            p = parcela.pagamento if parcela else None
            beneficios.append([b.colaborador_id, b.nome_fonte, b.get_tipo_display(), b.base, b.contrato,
                               parcela.semana if parcela else None, parcela.valor if parcela else None,
                               b.get_status_fonte_display(), b.get_status_conciliacao_display(),
                               p.get_status_display() if p else 'Não gerado', p.valor if p else None,
                               p.data_vencimento if p else None, p.data_pagamento if p else None,
                               b.pix, '; '.join(b.problemas)])
    return exportar_xlsx(
        titulo=f'Base Fiscal — {folha.competencia:%m/%Y} — v{folha.versao}',
        contexto=f'Lote #{folha.pk}: {folha.titulo}. Mesmos registros da tela. '
                 'Valores de origem e pagamentos do sistema são apresentados separadamente. '
                 'O gráfico de pagamentos inclui apenas lançamentos vinculados, sem cancelados.',
        abas=[('Folha', colunas, linhas), ('Benefícios', col_beneficios, beneficios)],
        graficos=dados['graficos'], nome=f'fiscal-{folha.competencia:%Y-%m}-lote-{folha.pk}-v{folha.versao}',
    )
