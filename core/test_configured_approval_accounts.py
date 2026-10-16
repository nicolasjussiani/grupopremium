from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador
from administrativo.models import DemandaAdministrativa
from core.approval_workflow import aprovador_para, usuario_e_aprovador
from core.models import AprovacaoRegistro
from core.payment_approvals import sincronizar_aprovacao_pagamento
from financeiro.models import DocumentoFinanceiro, LancamentoERP


class ConfiguredApprovalAccountsTests(TestCase):
    """Valida os logins confirmados usando os valores reais padrão de settings."""

    @classmethod
    def setUpTestData(cls):
        cls.luiz = User.objects.create_superuser('admin@construipem.com.br')
        cls.thiago = User.objects.create_user('thiago001')
        cls.ceo = User.objects.create_superuser('ceo_premium')
        cls.admin = User.objects.create_superuser('administrador_teste')
        cls.admin.groups.add(Group.objects.get_or_create(name='Admin_Global')[0])
        cls.mesmo_email = User.objects.create_user('outro_login', email='admin@construipem.com.br')
        cls.pessoa = Colaborador.objects.create(nome='Beneficiário de teste')
        cls.salario = PagamentoColaborador.objects.create(
            colaborador=cls.pessoa, tipo='salario', competencia=date(2026, 10, 1),
            data_vencimento=date(2026, 10, 10), valor='2000.00',
        )
        cls.vt = PagamentoColaborador.objects.create(
            colaborador=cls.pessoa, tipo='vale_transporte', competencia=date(2026, 10, 5),
            data_vencimento=date(2026, 10, 5), valor='100.00',
        )
        cls.documento = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='CONTAS-CONFIGURADAS', descricao='Fornecedor de teste',
            valor='300.00', situacao_pagamento='a_pagar', status='lancado',
        )
        cls.demanda = DemandaAdministrativa.objects.create(
            tipo='apoio_operacional', titulo='Operação de teste', descricao='Conferir operação',
            requisitante='Equipe',
        )
        cls.lancamento = LancamentoERP.objects.create(
            documento=cls.documento, descricao='Conferência contábil', tipo='debito',
            valor='300.00', centro_custo='Matriz', competencia=date(2026, 10, 1),
            status='em_validacao',
        )

    def setUp(self):
        telegram = patch('core.signals.enviar_mensagem_telegram')
        telegram.start()
        self.addCleanup(telegram.stop)

    def criar_filas(self):
        pagamentos = [sincronizar_aprovacao_pagamento(objeto) for objeto in (
            self.salario, self.vt, self.documento,
        )]
        operacionais = [
            AprovacaoRegistro.criar_para(self.demanda, 'Demanda', modulo='administrativo'),
            AprovacaoRegistro.criar_para(self.lancamento, 'Conferência', modulo='financeiro'),
        ]
        return pagamentos, operacionais

    def test_configuracao_padrao_resolve_os_logins_exatos_confirmados(self):
        self.assertEqual(settings.APROVADOR_PAGAMENTOS_USERNAME, 'admin@construipem.com.br')
        self.assertEqual(settings.APROVADOR_OPERACIONAL_USERNAME, 'thiago001')
        self.assertEqual(aprovador_para('pagamento'), self.luiz)
        self.assertEqual(aprovador_para('operacional'), self.thiago)
        self.assertFalse(usuario_e_aprovador(self.mesmo_email, 'pagamento'))

    def test_folha_vt_e_fornecedor_vao_para_luiz_e_operacao_para_thiago(self):
        pagamentos, operacionais = self.criar_filas()
        for aprovacao in pagamentos:
            with self.subTest(titulo=aprovacao.titulo):
                self.assertEqual(aprovacao.destinatario, self.luiz)
                self.assertEqual(aprovacao.finalidade, 'pagamento')
                self.assertTrue(aprovacao.dados_aprovacao)
        for aprovacao in operacionais:
            with self.subTest(titulo=aprovacao.titulo):
                self.assertEqual(aprovacao.destinatario, self.thiago)
                self.assertEqual(aprovacao.finalidade, 'operacional')

    def test_filas_e_decisoes_negam_acesso_cruzado_inclusive_admin_e_ceo(self):
        pagamentos, operacionais = self.criar_filas()
        for usuario, permitidas, negadas in (
            (self.luiz, pagamentos, operacionais),
            (self.thiago, operacionais, pagamentos),
            (self.admin, [], pagamentos + operacionais),
            (self.ceo, [], pagamentos + operacionais),
            (self.mesmo_email, [], pagamentos + operacionais),
        ):
            with self.subTest(username=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(reverse('aprovacoes_count_api')).json()['total'], len(permitidas))
                self.assertEqual(self.client.get(reverse('status_mobile')).json()['pendentes'], len(permitidas))
                for aprovacao in negadas:
                    self.assertEqual(self.client.get(
                        reverse('detalhe_aprovacao_mobile', args=[aprovacao.pk]),
                    ).status_code, 404)
                    for acao in ('aprovar_registro', 'rejeitar_registro'):
                        self.assertEqual(self.client.post(reverse(acao, args=[aprovacao.pk]), {
                            'motivo_rejeicao': 'Tentativa sem responsabilidade',
                        }).status_code, 404)
        self.assertEqual(AprovacaoRegistro.objects.filter(status='pendente').count(), 5)

    def test_contas_confirmadas_decidem_somente_sua_finalidade_sem_baixa_automatica(self):
        pagamentos, operacionais = self.criar_filas()
        self.client.force_login(self.luiz)
        for aprovacao in pagamentos:
            self.assertEqual(self.client.post(
                reverse('aprovar_registro', args=[aprovacao.pk]),
            ).status_code, 302)
            aprovacao.refresh_from_db()
            self.assertEqual(aprovacao.aprovado_por, self.luiz)
        self.salario.refresh_from_db()
        self.vt.refresh_from_db()
        self.documento.refresh_from_db()
        self.assertEqual(self.salario.status, 'pendente')
        self.assertEqual(self.vt.status, 'pendente')
        self.assertEqual(self.documento.situacao_pagamento, 'a_pagar')
        self.assertIsNone(self.documento.data_pagamento)
        self.client.force_login(self.thiago)
        for aprovacao in operacionais:
            self.assertEqual(self.client.post(
                reverse('aprovar_registro', args=[aprovacao.pk]),
            ).status_code, 302)
            aprovacao.refresh_from_db()
            self.assertEqual(aprovacao.aprovado_por, self.thiago)
        self.demanda.refresh_from_db()
        self.lancamento.refresh_from_db()
        self.assertEqual(self.demanda.status, 'em_execucao')
        self.assertEqual(self.lancamento.status, 'finalizado')

    def test_conta_confirmada_inativa_nao_faz_fallback_para_email_ou_administrador(self):
        User.objects.filter(pk=self.luiz.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            sincronizar_aprovacao_pagamento(self.salario)
        self.assertFalse(AprovacaoRegistro.objects.exists())
        for usuario in (self.luiz, self.mesmo_email, self.ceo, self.admin):
            self.assertFalse(usuario_e_aprovador(usuario, 'pagamento'))
