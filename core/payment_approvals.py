"""Autorizações nominais vinculadas aos dados exatos de cada pagamento."""

from datetime import date
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.approval_workflow import FINALIDADE_PAGAMENTO, aprovador_para
from core.models import AprovacaoRegistro, Notificacao


def _modelo(objeto):
    return objeto._meta.label_lower


def _valor_json(valor):
    if isinstance(valor, Decimal):
        return format(valor, '.2f')
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def snapshot_pagamento(objeto):
    """Status, comprovantes e observações não alteram a obrigação autorizada."""
    if _modelo(objeto) == 'admissional.pagamentocolaborador':
        campos = (
            'colaborador_id', 'tipo', 'competencia', 'competencia_fim', 'valor',
            'chave_pix', 'data_vencimento', 'dias_trabalhados', 'valor_diaria',
            'salario_base', 'gratificacao', 'faltas', 'outros_descontos',
        )
    elif _modelo(objeto) == 'financeiro.documentofinanceiro':
        campos = (
            'tipo', 'numero_documento', 'descricao', 'valor', 'cnpj_emitente',
            'razao_social_emitente', 'data_emissao', 'data_vencimento',
            'centro_custo', 'unidade', 'contratos_vinculados',
        )
    else:
        raise ValidationError('Este registro não representa uma obrigação de pagamento.')
    dados = {}
    for campo in campos:
        valor = getattr(objeto, campo)
        field = objeto._meta.get_field(campo)
        if valor is not None and isinstance(field, models.DecimalField):
            valor = Decimal(str(valor))
        if valor and isinstance(field, models.DateField) and isinstance(valor, str):
            valor = date.fromisoformat(valor)
        dados[campo] = _valor_json(valor)
    if _modelo(objeto) == 'admissional.pagamentocolaborador':
        # A identidade da ficha pode mudar sem alterar o pagamento. Consulte a
        # ficha persistida, inclusive quando o chamador possui uma relação em cache.
        modelo_colaborador = objeto._meta.get_field('colaborador').remote_field.model
        beneficiario = modelo_colaborador.objects.using(objeto._state.db or 'default').values(
            'nome', 'cpf',
        ).get(pk=objeto.colaborador_id)
        dados['beneficiario_nome'] = beneficiario['nome']
        dados['beneficiario_documento'] = beneficiario['cpf']
        if not dados['chave_pix']:
            # A folha também exibe PIX vindo das importações fiscais legadas.
            item = getattr(objeto, 'item_fiscal', None)
            parcela = getattr(objeto, 'parcela_fiscal', None)
            dados['chave_pix'] = (item.pix if item else '') or (parcela.beneficio.pix if parcela else '')
    return {
        'versao': 1,
        'modelo': _modelo(objeto),
        'objeto_id': objeto.pk,
        **dados,
    }


def _esta_pendente(objeto):
    if _modelo(objeto) == 'admissional.pagamentocolaborador':
        return objeto.status == 'pendente'
    if _modelo(objeto) == 'financeiro.documentofinanceiro':
        return objeto.status != 'cancelado' and objeto.situacao_pagamento == 'a_pagar'
    raise ValidationError('Este registro não representa uma obrigação de pagamento.')


def _aprovacoes(objeto):
    using = objeto._state.db or 'default'
    ct = ContentType.objects.db_manager(using).get_for_model(objeto)
    return AprovacaoRegistro.objects.using(using).filter(
        content_type=ct, object_id=objeto.pk,
    ).order_by('-criado_em', '-pk')


def _cancelar(registros, motivo):
    ids = list(registros.filter(status='pendente').values_list('pk', flat=True))
    registros.filter(status='pendente').update(
        status='cancelado', decidido_em=timezone.now(), comentario=motivo,
    )
    Notificacao.objects.using(registros.db).filter(
        tipo='gateway', url_acao__in=[reverse('detalhe_aprovacao_mobile', args=[pk]) for pk in ids],
    ).update(lida=True)


def sincronizar_aprovacao_pagamento(objeto, usuario=None, reenviar=False):
    """Cria uma decisão por versão, preservando pagamentos e decisões históricas.

    Sempre bloqueia a obrigação antes de suas aprovações. Chamadores que editam
    a obrigação devem usar a mesma ordem dentro de sua transação.
    """
    if not objeto.pk:
        raise ValidationError('Salve o pagamento antes de solicitar sua aprovação.')
    using = objeto._state.db or 'default'
    with transaction.atomic(using=using):
        atual = type(objeto).objects.using(using).select_for_update().get(pk=objeto.pk)
        registros = _aprovacoes(atual)
        list(registros.select_for_update().values_list('pk', flat=True))
        if not _esta_pendente(atual):
            _cancelar(registros, 'A obrigação deixou de estar pendente de pagamento.')
            ultima = registros.first()
            pago = (
                atual.status == 'pago' if _modelo(atual) == 'admissional.pagamentocolaborador'
                else atual.situacao_pagamento == 'pago'
            )
            if (not pago and ultima and ultima.finalidade == FINALIDADE_PAGAMENTO
                    and ultima.status == 'aprovado'):
                # A decisão original continua no histórico. Este evento impede
                # que a reativação da mesma obrigação reutilize sua autorização.
                AprovacaoRegistro.objects.using(using).create(
                    content_type_id=ultima.content_type_id, object_id=ultima.object_id,
                    modulo=ultima.modulo, nivel=ultima.nivel,
                    finalidade=FINALIDADE_PAGAMENTO, status='cancelado',
                    destinatario_id=ultima.destinatario_id, solicitado_por=usuario,
                    dados_aprovacao=ultima.dados_aprovacao,
                    titulo=f'Autorização encerrada: {ultima.titulo}'[:255],
                    descricao=f'Autorização #{ultima.pk} encerrada porque a obrigação deixou de estar pendente sem baixa de pagamento.',
                    comentario='Uma reativação da obrigação exige nova autorização de pagamento.',
                    decidido_em=timezone.now(),
                )
            return None
        dados = snapshot_pagamento(atual)
        ultima = registros.first()
        responsavel = aprovador_para(FINALIDADE_PAGAMENTO, using=using)
        if ultima and ultima.finalidade == FINALIDADE_PAGAMENTO and ultima.dados_aprovacao == dados:
            if ultima.status == 'pendente' and ultima.destinatario_id == responsavel.pk:
                _cancelar(registros.exclude(pk=ultima.pk), 'Solicitação duplicada substituída.')
                return ultima
            if (ultima.status == 'aprovado' and ultima.aprovado_por_id == responsavel.pk
                    and ultima.destinatario_id == responsavel.pk):
                _cancelar(registros.exclude(pk=ultima.pk), 'Solicitação duplicada substituída.')
                return ultima
            if ultima.status == 'rejeitado' and not reenviar:
                _cancelar(registros.exclude(pk=ultima.pk), 'Solicitação duplicada substituída.')
                return ultima
        _cancelar(registros, 'Dados ou responsável alterados; necessária nova autorização.')
        folha = _modelo(atual) == 'admissional.pagamentocolaborador'
        beneficiario = str(atual.colaborador) if folha else atual.razao_social_emitente
        titulo = f'Pagamento: {beneficiario or atual.numero_documento} — R$ {atual.valor:.2f}'
        descricao = (
            f'{atual.get_tipo_display()}. Valor: R$ {atual.valor:.2f}. '
            f'Vencimento: {atual.data_vencimento or "não informado"}. '
            'A autorização não confirma a realização do pagamento.'
        )
        return AprovacaoRegistro.criar_para(
            atual, titulo[:255], descricao,
            modulo='admissional' if folha else 'financeiro',
            solicitado_por=usuario, dados_aprovacao=dados,
        )


def validar_snapshot_pagamento(objeto, aprovacao):
    """Impede decidir uma solicitação que deixou de representar o pagamento."""
    if (
        objeto is None
        or not _esta_pendente(objeto)
        or aprovacao.finalidade != FINALIDADE_PAGAMENTO
        or aprovacao.dados_aprovacao != snapshot_pagamento(objeto)
        or _aprovacoes(objeto).values_list('pk', flat=True).first() != aprovacao.pk
    ):
        raise ValidationError('O pagamento mudou. Atualize a solicitação antes de decidir.')


def exigir_aprovacao_pagamento(objeto):
    """Verifica dados propostos antes da baixa, sem registrar pagamento efetuado."""
    using = objeto._state.db or 'default'
    with transaction.atomic(using=using):
        atual = type(objeto).objects.using(using).select_for_update().get(pk=objeto.pk)
        ultima = _aprovacoes(atual).select_for_update().first()
        responsavel = aprovador_para(FINALIDADE_PAGAMENTO, using=using)
        if (
            not _esta_pendente(atual)
            or ultima is None
            or ultima.finalidade != FINALIDADE_PAGAMENTO
            or ultima.status != 'aprovado'
            or ultima.aprovado_por_id != responsavel.pk
            or ultima.destinatario_id != responsavel.pk
            or ultima.dados_aprovacao != snapshot_pagamento(atual)
            or ultima.dados_aprovacao != snapshot_pagamento(objeto)
        ):
            raise ValidationError('Este pagamento precisa da autorização do responsável por pagamentos antes da baixa.')


def situacao_aprovacao_pagamento(objeto):
    ultima = _aprovacoes(objeto).first()
    try:
        responsavel = aprovador_para(FINALIDADE_PAGAMENTO, using=objeto._state.db)
    except ValidationError:
        return 'nao_solicitado'
    if (ultima and ultima.finalidade == FINALIDADE_PAGAMENTO
            and ultima.destinatario_id == responsavel.pk
            and ultima.dados_aprovacao == snapshot_pagamento(objeto)
            and (ultima.status != 'aprovado' or ultima.aprovado_por_id == responsavel.pk)):
        if ultima.status in {'pendente', 'aprovado', 'rejeitado'}:
            return ultima.status
    return 'nao_solicitado'
