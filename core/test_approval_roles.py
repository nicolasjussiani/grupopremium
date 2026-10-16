from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from admissional.models import Colaborador, PagamentoColaborador
from administrativo.models import DemandaAdministrativa
from core.approval_workflow import (
    aprovador_para, finalidade_para_objeto, usuario_e_aprovador,
)
from core.models import AprovacaoRegistro, Notificacao
from core.telegram_utils import enviar_mensagem_telegram
from core.views_aprovacao import _aprovacoes_do_usuario
from financeiro.models import DocumentoFinanceiro, LancamentoERP


@override_settings(
    APROVADOR_PAGAMENTOS_USERNAME='luiz_teste',
    APROVADOR_OPERACIONAL_USERNAME='thiago_teste',
)
class ApprovalRoleTests(TestCase):
    def setUp(self):
        self.luiz = User.objects.create_user('luiz_teste', first_name='Luiz Teste')
        self.thiago = User.objects.create_user('thiago_teste', first_name='Thiago Teste')
        self.ceo = User.objects.create_superuser('ceo_premium')
        self.admin = User.objects.create_superuser('admin_teste')
        self.admin.groups.add(Group.objects.get_or_create(name='Admin_Global')[0])
        self.demanda = DemandaAdministrativa.objects.create(
            tipo='apoio_operacional', titulo='Demanda de teste', descricao='Revisar operação',
            requisitante='Equipe',
        )
        self.documento = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='TESTE-ROLES', descricao='Fornecedor de teste',
            valor='150.00', status='lancado', situacao_pagamento='a_pagar',
        )

    def criar(self, objeto=None, **kwargs):
        return AprovacaoRegistro.criar_para(
            objeto=objeto or self.demanda, titulo='Aprovação de teste', **kwargs,
        )

    def test_classificacao_server_side_ignora_finalidade_destinatario_e_modulo_informados(self):
        aprovacao = AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(self.documento),
            object_id=self.documento.pk, titulo='Pagamento', modulo='compras',
            finalidade='operacional', destinatario=self.thiago,
        )
        self.assertEqual(aprovacao.finalidade, 'pagamento')
        self.assertEqual(aprovacao.destinatario, self.luiz)
        operacao = AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(self.demanda),
            object_id=self.demanda.pk, titulo='Operação', modulo='financeiro',
            finalidade='pagamento', destinatario=self.luiz,
        )
        self.assertEqual(operacao.finalidade, 'operacional')
        self.assertEqual(operacao.destinatario, self.thiago)

    def test_folha_e_vt_sao_pagamento_e_lancamento_contabil_e_operacional(self):
        pessoa = Colaborador.objects.create(nome='Pessoa de teste')
        for tipo in ('salario', 'vale_transporte'):
            pagamento = PagamentoColaborador.objects.create(
                colaborador=pessoa, tipo=tipo, competencia=date(2026, 10, 1),
                data_vencimento=date(2026, 10, 1), valor='100.00',
            )
            aprovacao = self.criar(pagamento)
            self.assertEqual(finalidade_para_objeto(pagamento), 'pagamento')
            self.assertEqual(aprovacao.finalidade, 'pagamento')
            self.assertEqual(aprovacao.destinatario, self.luiz)
        lancamento = LancamentoERP.objects.create(
            documento=self.documento, descricao='Contabilidade', tipo='debito',
            valor=150, centro_custo='Teste', competencia=date(2026, 10, 1),
        )
        self.assertEqual(finalidade_para_objeto(lancamento), 'operacional')
        self.assertEqual(self.criar(lancamento).destinatario, self.thiago)

    def test_save_pendente_corrige_destinatario_e_finalidade_mas_preserva_snapshot(self):
        snapshot = {'valor': '150.00', 'referencia': 'teste'}
        aprovacao = self.criar(self.documento, dados_aprovacao=snapshot)
        aprovacao.destinatario = self.ceo
        aprovacao.finalidade = 'operacional'
        aprovacao.save(update_fields=['destinatario', 'finalidade'])
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.destinatario, self.luiz)
        self.assertEqual(aprovacao.finalidade, 'pagamento')
        self.assertEqual(aprovacao.dados_aprovacao, snapshot)

    def test_filas_detalhes_e_contadores_respeitam_finalidade_sem_bypass_executivo(self):
        operacional = self.criar()
        pagamento = self.criar(self.documento)
        for usuario, permitidas, negadas in (
            (self.luiz, [pagamento], [operacional]),
            (self.thiago, [operacional], [pagamento]),
            (self.ceo, [], [pagamento, operacional]),
            (self.admin, [], [pagamento, operacional]),
        ):
            with self.subTest(usuario=usuario.username):
                self.assertSetEqual(
                    set(_aprovacoes_do_usuario(usuario).values_list('pk', flat=True)),
                    {item.pk for item in permitidas},
                )
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(reverse('aprovacoes_count_api')).json()['total'], len(permitidas))
                self.assertEqual(self.client.get(reverse('status_mobile')).json()['pendentes'], len(permitidas))
                for aprovacao in permitidas:
                    for tela in ('detalhe_aprovacao', 'detalhe_aprovacao_mobile'):
                        self.assertEqual(self.client.get(reverse(tela, args=[aprovacao.pk])).status_code, 200)
                for aprovacao in negadas:
                    for tela in ('detalhe_aprovacao', 'detalhe_aprovacao_mobile'):
                        self.assertEqual(self.client.get(reverse(tela, args=[aprovacao.pk])).status_code, 404)
                    for acao in ('aprovar_registro', 'rejeitar_registro'):
                        self.assertEqual(self.client.post(reverse(acao, args=[aprovacao.pk]), {
                            'motivo_rejeicao': 'Teste de acesso', 'finalidade': 'operacional',
                            'destinatario': usuario.pk,
                        }).status_code, 404)
        self.assertEqual(AprovacaoRegistro.objects.filter(status='pendente').count(), 2)

    def test_pendencia_sem_destinatario_ou_com_finalidade_incorreta_nao_e_assumida(self):
        pagamento = self.criar(self.documento)
        for valores in (
            {'destinatario': None, 'finalidade': 'pagamento'},
            {'destinatario': self.thiago, 'finalidade': 'pagamento'},
            {'destinatario': self.thiago, 'finalidade': 'operacional'},
        ):
            AprovacaoRegistro.objects.filter(pk=pagamento.pk).update(**valores)
            for usuario in (self.luiz, self.thiago, self.ceo):
                self.assertFalse(_aprovacoes_do_usuario(usuario).filter(pk=pagamento.pk).exists())

    def test_responsavel_operacional_aprova_normalmente(self):
        aprovacao = self.criar(modulo='administrativo')
        self.client.force_login(self.thiago)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 302)
        aprovacao.refresh_from_db()
        self.demanda.refresh_from_db()
        self.assertEqual(aprovacao.aprovado_por, self.thiago)
        self.assertEqual(self.demanda.status, 'em_execucao')

    def test_aprovacao_de_pagamento_valida_snapshot_sem_marcar_documento_pago(self):
        aprovacao = self.criar(self.documento, modulo='financeiro', dados_aprovacao={'valor': '150.00'})
        self.client.force_login(self.luiz)
        with patch('core.payment_approvals.validar_snapshot_pagamento') as validar:
            response = self.client.post(reverse('aprovar_registro', args=[aprovacao.pk]))
        self.assertEqual(response.status_code, 302)
        validar.assert_called_once()
        self.assertEqual(validar.call_args.args[0].pk, self.documento.pk)
        self.assertEqual(validar.call_args.args[1].dados_aprovacao, {'valor': '150.00'})
        self.documento.refresh_from_db()
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'aprovado')
        self.assertEqual(aprovacao.aprovado_por, self.luiz)
        self.assertEqual(self.documento.situacao_pagamento, 'a_pagar')
        self.assertEqual(self.documento.status, 'lancado')
        self.assertIsNone(self.documento.data_pagamento)

    def test_snapshot_invalido_desfaz_decisao_e_preserva_pendencia(self):
        aprovacao = self.criar(self.documento)
        self.client.force_login(self.luiz)
        with patch('core.payment_approvals.validar_snapshot_pagamento', side_effect=ValidationError('Valor mudou')):
            response = self.client.post(reverse('aprovar_registro', args=[aprovacao.pk]))
        self.assertEqual(response.status_code, 400)
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'pendente')
        self.assertIsNone(aprovacao.aprovado_por)
        self.assertIsNone(aprovacao.decidido_em)

    def test_historico_nao_e_reencaminhado_quando_configuracao_muda(self):
        decidido_em = timezone.now()
        aprovacao = AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(self.documento),
            object_id=self.documento.pk, titulo='Decisão antiga', status='aprovado',
            destinatario=self.ceo, aprovado_por=self.ceo, nivel=1,
            finalidade='operacional', decidido_em=decidido_em, dados_aprovacao={'legado': True},
        )
        with override_settings(APROVADOR_PAGAMENTOS_USERNAME='', APROVADOR_OPERACIONAL_USERNAME=''):
            aprovacao.comentario = 'Histórico preservado'
            aprovacao.save(update_fields=['comentario'])
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.destinatario, self.ceo)
        self.assertEqual(aprovacao.aprovado_por, self.ceo)
        self.assertEqual(aprovacao.nivel, 1)
        self.assertEqual(aprovacao.finalidade, 'operacional')
        self.assertEqual(aprovacao.decidido_em, decidido_em)
        self.assertEqual(aprovacao.dados_aprovacao, {'legado': True})
        self.assertTrue(_aprovacoes_do_usuario(self.ceo).filter(pk=aprovacao.pk).exists())

    def test_configuracao_ausente_inativa_inexata_ou_sobreposta_falha_sem_fallback(self):
        for username in ('', 'usuario_inexistente', 'LUIZ_TESTE', 'thiago_teste'):
            with self.subTest(username=username), override_settings(APROVADOR_PAGAMENTOS_USERNAME=username):
                with self.assertRaises(ValidationError):
                    self.criar(self.documento)
                self.assertFalse(usuario_e_aprovador(self.luiz, 'pagamento'))
        User.objects.filter(pk=self.luiz.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            aprovador_para('pagamento')
        self.assertFalse(usuario_e_aprovador(self.luiz, 'pagamento'))
        self.assertFalse(AprovacaoRegistro.objects.exists())
        self.assertFalse(Notificacao.objects.exists())

    def test_notificacoes_e_canais_telegram_sao_do_responsavel_correto(self):
        with patch('core.signals.enviar_mensagem_telegram') as enviar:
            with self.captureOnCommitCallbacks(execute=True):
                operacional = self.criar()
                pagamento = self.criar(self.documento)
        self.assertEqual([chamada.args[0] for chamada in enviar.call_args_list], [
            'aprovacoes_operacionais', 'aprovacoes_pagamento',
        ])
        for aprovacao, usuario, nome in (
            (operacional, self.thiago, 'Thiago Teste'),
            (pagamento, self.luiz, 'Luiz Teste'),
        ):
            aviso = Notificacao.objects.get(url_acao=reverse('detalhe_aprovacao_mobile', args=[aprovacao.pk]))
            self.assertEqual(aviso.destinatario, usuario)
            self.assertIn(nome, aviso.mensagem)
            self.assertNotIn('ceo_premium', aviso.mensagem)


class ExclusiveTelegramChannelTests(SimpleTestCase):
    def test_falta_de_canal_exclusivo_nao_envia_ao_default_ou_outro_responsavel(self):
        for canal in ('aprovacoes_pagamento', 'aprovacoes_operacionais'):
            with self.subTest(canal=canal), patch.dict('os.environ', {
                'TELEGRAM_BOT_TOKEN': 'token-geral-teste', 'TELEGRAM_CEO_CHAT_ID': 'chat-geral-teste',
            }, clear=True), patch('core.telegram_utils.threading.Thread') as thread:
                enviar_mensagem_telegram(canal, 'Teste de canal')
                thread.assert_not_called()

    def test_envio_usa_token_e_chat_do_canal_exclusivo(self):
        for canal, sufixo in (
            ('aprovacoes_pagamento', 'PAGAMENTO'),
            ('aprovacoes_operacionais', 'OPERACIONAIS'),
        ):
            with self.subTest(canal=canal), patch.dict('os.environ', {
                f'TELEGRAM_TOKEN_APROVACOES_{sufixo}': 'token-especifico-teste',
                f'TELEGRAM_CHAT_ID_APROVACOES_{sufixo}': 'chat-especifico-teste',
                'TELEGRAM_BOT_TOKEN': 'token-geral-teste', 'TELEGRAM_CEO_CHAT_ID': 'chat-geral-teste',
            }, clear=True), patch('core.telegram_utils.threading.Thread') as thread, \
                    patch('core.telegram_utils.requests.post') as post:
                post.return_value.status_code = 200
                enviar_mensagem_telegram(canal, 'Teste de canal')
                thread.return_value.start.assert_called_once()
                thread.call_args.kwargs['target']()
                self.assertEqual(post.call_args.args[0], 'https://api.telegram.org/bottoken-especifico-teste/sendMessage')
                self.assertEqual(post.call_args.kwargs['json']['chat_id'], 'chat-especifico-teste')
