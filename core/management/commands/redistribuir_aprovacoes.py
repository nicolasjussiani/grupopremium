"""Ativa a divisão nominal sem reescrever decisões históricas."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse

from core.approval_workflow import (
    FINALIDADE_OPERACIONAL, FINALIDADE_PAGAMENTO, aprovador_para,
    finalidade_para_content_type,
)
from core.models import AprovacaoRegistro, LogAtividade, Notificacao
from core.payment_approvals import _cancelar, sincronizar_aprovacao_pagamento


class Command(BaseCommand):
    help = 'Confere responsáveis e redistribui somente pendências. Use --apply para gravar.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Gravar a redistribuição e novas solicitações.')

    def handle(self, *args, **options):
        from admissional.models import PagamentoColaborador
        from financeiro.models import DocumentoFinanceiro

        try:
            responsaveis = {finalidade: aprovador_para(finalidade) for finalidade in (
                FINALIDADE_OPERACIONAL, FINALIDADE_PAGAMENTO,
            )}
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        for finalidade, usuario in responsaveis.items():
            self.stdout.write(f'{finalidade}: {usuario.username} (ID {usuario.pk})')
        pendentes = AprovacaoRegistro.objects.filter(status='pendente')
        folha = PagamentoColaborador.objects.filter(status='pendente')
        documentos = DocumentoFinanceiro.objects.filter(situacao_pagamento='a_pagar').exclude(status='cancelado')
        self.stdout.write(
            f'{pendentes.count()} solicitações pendentes; '
            f'{folha.count()} pagamentos de colaboradores e {documentos.count()} contas a pagar para conferir.'
        )
        if not options['apply']:
            self.stdout.write('Simulação concluída. Nenhum registro alterado. Use --apply para gravar.')
            return
        try:
            with transaction.atomic():
                alteradas, canceladas = self._redistribuir(responsaveis)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS(
            f'{alteradas} aprovações operacionais redistribuídas; '
            f'{canceladas} pendências sem origem canceladas; pagamentos conferidos. Histórico preservado.'
        ))

    def _redistribuir(self, responsaveis):
        from admissional.models import PagamentoColaborador
        from financeiro.models import DocumentoFinanceiro

        alteradas = canceladas = 0
        pendentes = AprovacaoRegistro.objects.filter(status='pendente')
        # Origens são bloqueadas antes da aprovação, como nas telas de decisão.
        for pk in pendentes.order_by('pk').values_list('pk', flat=True):
            referencia = AprovacaoRegistro.objects.select_related('content_type').get(pk=pk)
            finalidade = finalidade_para_content_type(referencia.content_type)
            objeto = referencia.objeto
            if finalidade == FINALIDADE_PAGAMENTO and objeto is not None:
                # O serviço abaixo trata snapshots antigos e cancelamentos.
                continue
            if objeto is not None:
                # Manutenção protege primeiro o ativo; lançamentos, o documento.
                if objeto._meta.label_lower == 'manutencao.registromanutencao':
                    type(objeto.ativo).objects.select_for_update().get(pk=objeto.ativo_id)
                if objeto._meta.label_lower == 'financeiro.lancamentoerp':
                    DocumentoFinanceiro.objects.select_for_update().get(pk=objeto.documento_id)
                type(objeto).objects.select_for_update().get(pk=objeto.pk)
            aprovacao = AprovacaoRegistro.objects.select_for_update().get(pk=pk)
            if aprovacao.status != 'pendente':
                continue
            if aprovacao.objeto is None:
                _cancelar(AprovacaoRegistro.objects.filter(pk=pk), 'O registro de origem não existe mais.')
                canceladas += 1
                continue
            responsavel = responsaveis[finalidade]
            if (aprovacao.destinatario_id == responsavel.pk
                    and aprovacao.finalidade == finalidade and aprovacao.nivel == 2):
                continue
            anterior = aprovacao.destinatario_id
            aprovacao.save(update_fields=['destinatario', 'finalidade', 'nivel'])
            url = reverse('detalhe_aprovacao_mobile', args=[pk])
            Notificacao.objects.filter(tipo='gateway', url_acao=url).delete()
            Notificacao.objects.create(
                destinatario=responsavel, tipo='gateway', modulo=aprovacao.modulo,
                titulo=aprovacao.titulo[:200], url_acao=url,
                mensagem=f'Solicitação encaminhada para {responsavel.get_full_name() or responsavel.username}.',
            )
            LogAtividade.objects.create(
                acao='Redistribuição de aprovação pendente', modulo=aprovacao.modulo,
                url=url, detalhes=f'Aprovação {pk}; destinatário {anterior} → {responsavel.pk}; {finalidade}.',
            )
            alteradas += 1
        for modelo in (PagamentoColaborador, DocumentoFinanceiro):
            # Inclui origens com solicitações antigas para cancelar filas obsoletas.
            for objeto in modelo.objects.order_by('pk').iterator():
                sincronizar_aprovacao_pagamento(objeto)
        return alteradas, canceladas
