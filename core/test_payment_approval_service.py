from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from admissional.models import Colaborador, PagamentoColaborador
from administrativo.models import DemandaAdministrativa
from core.models import AprovacaoRegistro, LogAtividade, Notificacao
from core.payment_approvals import (
    exigir_aprovacao_pagamento, sincronizar_aprovacao_pagamento,
    situacao_aprovacao_pagamento, snapshot_pagamento, validar_snapshot_pagamento,
)
from financeiro.models import DocumentoFinanceiro


class PaymentApprovalTestData:
    def setUp(self):
        self.telegram = patch('core.signals.enviar_mensagem_telegram').start()
        self.addCleanup(patch.stopall)
        self.luiz = User.objects.create_user('luiz_teste')
        self.thiago = User.objects.create_user('thiago_teste')
        self.legado = User.objects.create_superuser('ceo_premium')
        self.pessoa = Colaborador.objects.create(nome='Colaborador de teste')
        self.pagamento = PagamentoColaborador.objects.create(
            colaborador=self.pessoa, tipo='salario', competencia=date(2026, 10, 1),
            data_vencimento=date(2026, 10, 10), valor=Decimal('1500.00'),
            chave_pix='beneficiario@example.test',
        )
        self.documento = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='TESTE-SERVICO', descricao='Fornecedor de teste',
            valor=Decimal('100.00'), situacao_pagamento='a_pagar', status='lancado',
            razao_social_emitente='Fornecedor de teste',
        )

    def decidir(self, aprovacao, status='aprovado'):
        self.client.force_login(self.luiz)
        acao = 'aprovar_registro' if status == 'aprovado' else 'rejeitar_registro'
        response = self.client.post(reverse(acao, args=[aprovacao.pk]), {
            'motivo_rejeicao': 'Corrigir a solicitação de teste',
        })
        self.assertEqual(response.status_code, 302, response.content[:300])
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, status)

    def registros(self, objeto):
        return AprovacaoRegistro.objects.filter(
            content_type=ContentType.objects.get_for_model(objeto), object_id=objeto.pk,
        )


@override_settings(
    APROVADOR_PAGAMENTOS_USERNAME='luiz_teste',
    APROVADOR_OPERACIONAL_USERNAME='thiago_teste',
)
class PaymentApprovalServiceTests(PaymentApprovalTestData, TestCase):
    def test_sincronizacao_repetida_reutiliza_solicitacao_e_autorizacao(self):
        for objeto in (self.pagamento, self.documento):
            with self.subTest(modelo=objeto._meta.label_lower):
                primeira = sincronizar_aprovacao_pagamento(objeto)
                for _ in range(3):
                    self.assertEqual(sincronizar_aprovacao_pagamento(objeto).pk, primeira.pk)
                self.decidir(primeira)
                self.assertEqual(sincronizar_aprovacao_pagamento(objeto).pk, primeira.pk)
                exigir_aprovacao_pagamento(objeto)
                self.assertEqual(self.registros(objeto).count(), 1)
                self.assertEqual(Notificacao.objects.filter(
                    url_acao=reverse('detalhe_aprovacao_mobile', args=[primeira.pk]),
                ).count(), 1)

    def test_alteracao_de_valor_exige_nova_decisao_e_preserva_anterior(self):
        for objeto in (self.pagamento, self.documento):
            with self.subTest(modelo=objeto._meta.label_lower):
                anterior = sincronizar_aprovacao_pagamento(objeto)
                self.decidir(anterior)
                historico = self.registros(objeto).get(pk=anterior.pk).__dict__.copy()
                objeto.valor += Decimal('1.00')
                objeto.save(update_fields=['valor'])
                with self.assertRaises(ValidationError):
                    exigir_aprovacao_pagamento(objeto)
                with self.assertRaises(ValidationError):
                    validar_snapshot_pagamento(objeto, anterior)
                self.assertEqual(situacao_aprovacao_pagamento(objeto), 'nao_solicitado')
                nova = sincronizar_aprovacao_pagamento(objeto)
                self.assertNotEqual(nova.pk, anterior.pk)
                self.assertEqual(nova.status, 'pendente')
                self.assertEqual(nova.dados_aprovacao['valor'], format(objeto.valor, '.2f'))
                anterior.refresh_from_db()
                for campo in ('status', 'destinatario_id', 'aprovado_por_id', 'decidido_em', 'dados_aprovacao'):
                    self.assertEqual(getattr(anterior, campo), historico[campo])

    def test_rejeicao_exige_reenvio_explicito_para_mesmos_dados(self):
        rejeitada = sincronizar_aprovacao_pagamento(self.pagamento)
        self.decidir(rejeitada, 'rejeitado')
        for _ in range(2):
            self.assertEqual(sincronizar_aprovacao_pagamento(self.pagamento).pk, rejeitada.pk)
        self.assertEqual(situacao_aprovacao_pagamento(self.pagamento), 'rejeitado')
        self.assertEqual(self.registros(self.pagamento).count(), 1)
        with self.assertRaises(ValidationError):
            exigir_aprovacao_pagamento(self.pagamento)
        nova = sincronizar_aprovacao_pagamento(self.pagamento, reenviar=True)
        self.assertEqual(nova.status, 'pendente')
        self.assertNotEqual(nova.pk, rejeitada.pk)
        self.assertEqual(sincronizar_aprovacao_pagamento(self.pagamento, reenviar=True).pk, nova.pk)
        rejeitada.refresh_from_db()
        self.assertEqual(rejeitada.status, 'rejeitado')
        self.assertEqual(rejeitada.motivo_rejeicao, 'Corrigir a solicitação de teste')

    def test_retirada_invalida_autorizacao_sem_reutiliza_la_ao_reativar(self):
        for objeto in (self.pagamento, self.documento):
            with self.subTest(modelo=objeto._meta.label_lower):
                autorizada = sincronizar_aprovacao_pagamento(objeto)
                self.decidir(autorizada)
                historico = self.registros(objeto).get(pk=autorizada.pk).__dict__.copy()
                status_original = objeto.status
                objeto.status = 'cancelado'
                objeto.save(update_fields=['status'])
                # Encerrar uma obrigação não depende de contas ainda configuradas.
                with override_settings(APROVADOR_PAGAMENTOS_USERNAME=''):
                    self.assertIsNone(sincronizar_aprovacao_pagamento(objeto))
                    self.assertIsNone(sincronizar_aprovacao_pagamento(objeto))
                evento = self.registros(objeto).first()
                self.assertEqual(self.registros(objeto).count(), 2)
                self.assertEqual(evento.status, 'cancelado')
                self.assertIsNone(evento.aprovado_por)
                self.assertIn(f'#{autorizada.pk}', evento.descricao)
                autorizada.refresh_from_db()
                for campo in ('status', 'destinatario_id', 'aprovado_por_id', 'decidido_em', 'dados_aprovacao'):
                    self.assertEqual(getattr(autorizada, campo), historico[campo])
                objeto.status = status_original
                objeto.save(update_fields=['status'])
                self.assertEqual(snapshot_pagamento(objeto), autorizada.dados_aprovacao)
                with self.assertRaises(ValidationError):
                    exigir_aprovacao_pagamento(objeto)
                nova = sincronizar_aprovacao_pagamento(objeto)
                self.assertEqual(nova.status, 'pendente')
                self.assertNotEqual(nova.pk, autorizada.pk)
                with self.assertRaises(ValidationError):
                    exigir_aprovacao_pagamento(objeto)
                self.decidir(nova)
                exigir_aprovacao_pagamento(objeto)

    def test_campos_financeiros_propostos_na_baixa_exigem_mesmo_snapshot(self):
        outra_pessoa = Colaborador.objects.create(nome='Outro colaborador de teste')
        alteracoes = (
            (self.pagamento, {
                'colaborador_id': outra_pessoa.pk, 'tipo': 'reembolso',
                'competencia': date(2026, 11, 1), 'competencia_fim': date(2026, 11, 30),
                'valor': Decimal('1501.00'), 'chave_pix': 'outra-chave@example.test',
                'data_vencimento': date(2026, 10, 11), 'dias_trabalhados': Decimal('2.00'),
                'valor_diaria': Decimal('10.00'), 'salario_base': Decimal('1501.00'),
                'gratificacao': Decimal('1.00'), 'faltas': Decimal('1.00'),
                'outros_descontos': Decimal('1.00'),
            }),
            (self.documento, {
                'tipo': 'reembolso', 'numero_documento': 'OUTRO', 'descricao': 'Outro serviço',
                'valor': Decimal('101.00'), 'cnpj_emitente': '12.345.678/0001-00',
                'razao_social_emitente': 'Outro fornecedor', 'data_emissao': date(2026, 10, 1),
                'data_vencimento': date(2026, 10, 30), 'centro_custo': 'Outro centro',
                'unidade': 'Outra unidade', 'contratos_vinculados': 'Outro contrato',
            }),
        )
        for objeto, campos in alteracoes:
            self.decidir(sincronizar_aprovacao_pagamento(objeto))
            for campo, valor in campos.items():
                with self.subTest(modelo=objeto._meta.label_lower, campo=campo):
                    proposto = type(objeto).objects.get(pk=objeto.pk)
                    setattr(proposto, campo, valor)
                    with self.assertRaises(ValidationError):
                        exigir_aprovacao_pagamento(proposto)

    def test_pagamento_efetivamente_quitado_preserva_autorizacao_sem_evento_cancelado(self):
        for objeto in (self.pagamento, self.documento):
            with self.subTest(modelo=objeto._meta.label_lower):
                autorizada = sincronizar_aprovacao_pagamento(objeto)
                self.decidir(autorizada)
                if isinstance(objeto, PagamentoColaborador):
                    objeto.status = 'pago'
                else:
                    objeto.situacao_pagamento = 'pago'
                objeto.data_pagamento = date(2026, 10, 10)
                objeto.save()
                self.assertIsNone(sincronizar_aprovacao_pagamento(objeto))
                self.assertIsNone(sincronizar_aprovacao_pagamento(objeto))
                autorizada.refresh_from_db()
                self.assertEqual(autorizada.status, 'aprovado')
                self.assertEqual(self.registros(objeto).count(), 1)
                self.assertEqual(self.registros(objeto).first().pk, autorizada.pk)

    def test_alteracao_da_identidade_na_ficha_exige_nova_aprovacao_sem_cache_obsoleto(self):
        for campo, valor in (('nome', 'Outro nome de teste'), ('cpf', '123.456.789-09')):
            with self.subTest(campo=campo):
                autorizada = sincronizar_aprovacao_pagamento(self.pagamento)
                if autorizada.status == 'pendente':
                    self.decidir(autorizada)
                # Este objeto mantém a relação Colaborador antiga em memória.
                _ = self.pagamento.colaborador.nome
                Colaborador.objects.filter(pk=self.pessoa.pk).update(**{campo: valor})
                with self.assertRaises(ValidationError):
                    exigir_aprovacao_pagamento(self.pagamento)
                self.assertEqual(situacao_aprovacao_pagamento(self.pagamento), 'nao_solicitado')
                nova = sincronizar_aprovacao_pagamento(self.pagamento)
                self.assertNotEqual(nova.pk, autorizada.pk)
                chave = 'beneficiario_nome' if campo == 'nome' else 'beneficiario_documento'
                self.assertEqual(nova.dados_aprovacao[chave], valor)
                self.decidir(nova)
                exigir_aprovacao_pagamento(self.pagamento)

    def test_observacao_e_dados_da_baixa_nao_alteram_obrigacao(self):
        self.decidir(sincronizar_aprovacao_pagamento(self.pagamento))
        self.pagamento.observacao = 'Comprovante conferido'
        self.pagamento.status = 'pago'
        self.pagamento.data_pagamento = date(2026, 10, 10)
        exigir_aprovacao_pagamento(self.pagamento)

    def test_decisao_mais_antiga_nao_autoriza_apos_reenvio(self):
        antiga = sincronizar_aprovacao_pagamento(self.documento)
        self.decidir(antiga)
        nova = AprovacaoRegistro.criar_para(
            self.documento, 'Nova análise', dados_aprovacao=snapshot_pagamento(self.documento),
        )
        with self.assertRaises(ValidationError):
            exigir_aprovacao_pagamento(self.documento)
        with self.assertRaises(ValidationError):
            validar_snapshot_pagamento(self.documento, antiga)
        validar_snapshot_pagamento(self.documento, nova)

    def test_baixa_rejeita_finalidade_ou_destinatario_adulterados(self):
        aprovacao = sincronizar_aprovacao_pagamento(self.documento)
        self.decidir(aprovacao)
        for valores in (
            {'finalidade': 'operacional', 'destinatario': self.luiz},
            {'finalidade': 'pagamento', 'destinatario': self.thiago},
            {'finalidade': 'pagamento', 'destinatario': None},
        ):
            with self.subTest(valores=valores):
                AprovacaoRegistro.objects.filter(pk=aprovacao.pk).update(**valores)
                with self.assertRaises(ValidationError):
                    exigir_aprovacao_pagamento(self.documento)

    def test_reuso_de_decisao_final_cancela_duplicatas_pendentes(self):
        for status in ('aprovado', 'rejeitado'):
            with self.subTest(status=status):
                duplicada = AprovacaoRegistro.criar_para(self.documento, 'Duplicata antiga')
                ultima = AprovacaoRegistro.criar_para(
                    self.documento, 'Solicitação atual', dados_aprovacao=snapshot_pagamento(self.documento),
                )
                self.decidir(ultima, status)
                self.assertEqual(sincronizar_aprovacao_pagamento(self.documento).pk, ultima.pk)
                duplicada.refresh_from_db()
                self.assertEqual(duplicada.status, 'cancelado')
                self.assertFalse(self.registros(self.documento).filter(status='pendente').exists())
                self.assertTrue(Notificacao.objects.get(
                    url_acao=reverse('detalhe_aprovacao_mobile', args=[duplicada.pk]),
                ).lida)

    def test_origem_quitada_ou_cancelada_cancela_pendencia_legada_sem_responsavel(self):
        casos = (
            (self.pagamento, {'status': 'pago'}),
            (self.pagamento, {'status': 'cancelado'}),
            (self.documento, {'status': 'cancelado'}),
            (self.documento, {'status': 'lancado', 'situacao_pagamento': 'pago'}),
            (self.documento, {'status': 'lancado', 'situacao_pagamento': 'a_receber'}),
        )
        for objeto, alteracoes in casos:
            with self.subTest(modelo=objeto._meta.label_lower, alteracoes=alteracoes):
                antiga = AprovacaoRegistro.criar_para(objeto, 'Fila legada')
                AprovacaoRegistro.objects.filter(pk=antiga.pk).update(
                    finalidade='operacional', destinatario=self.legado,
                )
                type(objeto).objects.filter(pk=objeto.pk).update(**alteracoes)
                with override_settings(APROVADOR_PAGAMENTOS_USERNAME=''):
                    self.assertIsNone(sincronizar_aprovacao_pagamento(objeto))
                antiga.refresh_from_db()
                self.assertEqual(antiga.status, 'cancelado')
                self.assertEqual(antiga.finalidade, 'operacional')
                self.assertEqual(antiga.destinatario, self.legado)
                self.assertTrue(Notificacao.objects.get(
                    url_acao=reverse('detalhe_aprovacao_mobile', args=[antiga.pk]),
                ).lida)

    def test_sincronizacao_rele_estado_depois_do_bloqueio_da_origem(self):
        aprovacao = sincronizar_aprovacao_pagamento(self.documento)
        obter = QuerySet.get
        mudou = False

        def alterar_antes_do_lock(queryset, *args, **kwargs):
            nonlocal mudou
            if queryset.model is DocumentoFinanceiro and queryset.query.select_for_update and not mudou:
                mudou = True
                DocumentoFinanceiro.objects.filter(pk=self.documento.pk).update(status='cancelado')
            return obter(queryset, *args, **kwargs)

        with patch.object(QuerySet, 'get', alterar_antes_do_lock):
            self.assertIsNone(sincronizar_aprovacao_pagamento(self.documento))
        self.assertTrue(mudou)
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'cancelado')

    def test_pagamento_nao_salvo_ou_modelo_indevido_nao_cria_aprovacao(self):
        with self.assertRaises(ValidationError):
            sincronizar_aprovacao_pagamento(PagamentoColaborador())
        with self.assertRaises(ValidationError):
            snapshot_pagamento(self.pessoa)
        self.assertFalse(AprovacaoRegistro.objects.exists())


@override_settings(
    APROVADOR_PAGAMENTOS_USERNAME='luiz_teste',
    APROVADOR_OPERACIONAL_USERNAME='thiago_teste',
)
class PaymentApprovalBackfillTests(PaymentApprovalTestData, TestCase):
    def preparar_legado(self):
        demanda = DemandaAdministrativa.objects.create(
            tipo='apoio_operacional', titulo='Pedido de teste', descricao='Operação', requisitante='Equipe',
        )
        operacional = AprovacaoRegistro.criar_para(demanda, 'Operacional antiga', modulo='administrativo')
        pagamento = AprovacaoRegistro.criar_para(self.documento, 'Pagamento antigo', modulo='financeiro')
        AprovacaoRegistro.objects.filter(pk__in=(operacional.pk, pagamento.pk)).update(
            finalidade='operacional', destinatario=self.legado, nivel=1,
        )
        Notificacao.objects.filter(tipo='gateway').update(destinatario=self.legado)
        historico = AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(self.documento), object_id=self.documento.pk,
            titulo='Decisão histórica', status='rejeitado', finalidade='operacional',
            destinatario=self.legado, aprovado_por=self.legado, decidido_em=timezone.now(),
            dados_aprovacao={'historico': True},
        )
        return operacional, pagamento, historico

    def estado(self):
        return tuple(list(modelo.objects.order_by('pk').values()) for modelo in (
            AprovacaoRegistro, Notificacao, LogAtividade, PagamentoColaborador, DocumentoFinanceiro,
        ))

    def comando(self, aplicar=False):
        saida = StringIO()
        call_command('redistribuir_aprovacoes', apply=aplicar, stdout=saida)
        return saida.getvalue()

    def test_simulacao_nao_altera_dados_ou_envia_notificacao(self):
        self.preparar_legado()
        antes = self.estado()
        with self.captureOnCommitCallbacks(execute=True):
            saida = self.comando()
        self.assertIn('Simulação concluída', saida)
        self.assertEqual(self.estado(), antes)
        self.telegram.assert_not_called()

    def test_conta_ausente_ou_inativa_impede_toda_redistribuicao(self):
        self.preparar_legado()
        antes = self.estado()
        with override_settings(APROVADOR_PAGAMENTOS_USERNAME='inexistente'):
            with self.assertRaises(CommandError):
                self.comando(aplicar=True)
        self.luiz.is_active = False
        self.luiz.save(update_fields=['is_active'])
        with self.assertRaises(CommandError):
            self.comando(aplicar=True)
        self.assertEqual(self.estado(), antes)

    def test_falha_durante_pagamentos_reverte_redistribuicao_e_novas_filas(self):
        self.preparar_legado()
        antes = self.estado()

        def sincronizar_e_falhar(objeto):
            if isinstance(objeto, DocumentoFinanceiro):
                raise ValidationError('Conta de pagamento indisponível durante a execução')
            return sincronizar_aprovacao_pagamento(objeto)

        with self.captureOnCommitCallbacks(execute=True), patch(
            'core.management.commands.redistribuir_aprovacoes.sincronizar_aprovacao_pagamento',
            side_effect=sincronizar_e_falhar,
        ):
            with self.assertRaises(CommandError):
                self.comando(aplicar=True)
        self.assertEqual(self.estado(), antes)
        self.telegram.assert_not_called()

    def test_aplicacao_idempotente_reencaminha_pendencias_e_preserva_historico(self):
        operacional, antiga, historico = self.preparar_legado()
        dados_historico = AprovacaoRegistro.objects.filter(pk=historico.pk).values().get()
        self.comando(aplicar=True)
        operacional.refresh_from_db()
        antiga.refresh_from_db()
        self.assertEqual(operacional.destinatario, self.thiago)
        self.assertEqual(operacional.finalidade, 'operacional')
        self.assertEqual(operacional.nivel, 2)
        self.assertEqual(antiga.status, 'cancelado')
        self.assertEqual(AprovacaoRegistro.objects.filter(pk=historico.pk).values().get(), dados_historico)
        for objeto in (self.pagamento, self.documento):
            atual = self.registros(objeto).get(status='pendente')
            self.assertEqual(atual.destinatario, self.luiz)
            self.assertEqual(atual.finalidade, 'pagamento')
            self.assertEqual(atual.dados_aprovacao, snapshot_pagamento(objeto))
        self.assertEqual(LogAtividade.objects.filter(acao='Redistribuição de aprovação pendente').count(), 1)
        depois = self.estado()
        self.comando(aplicar=True)
        self.assertEqual(self.estado(), depois)

    def test_comando_cancela_filas_legadas_de_origens_canceladas_e_orfas(self):
        _, antiga, _ = self.preparar_legado()
        DocumentoFinanceiro.objects.filter(pk=self.documento.pk).update(status='cancelado')
        orfa = AprovacaoRegistro.criar_para(self.documento, 'Origem removida')
        AprovacaoRegistro.objects.filter(pk=orfa.pk).update(object_id=999999, finalidade='operacional')
        self.comando(aplicar=True)
        for registro in (antiga, orfa):
            registro.refresh_from_db()
            self.assertEqual(registro.status, 'cancelado')
            self.assertTrue(Notificacao.objects.get(
                url_acao=reverse('detalhe_aprovacao_mobile', args=[registro.pk]),
            ).lida)
