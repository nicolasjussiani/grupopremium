from datetime import date
from importlib import import_module
from types import SimpleNamespace

from django.contrib.auth.models import Group, User
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.urls import reverse

from core.models import AprovacaoRegistro, Notificacao, PerfilUsuario
from core.approval_test_utils import configurar_aprovadores
from financeiro.models import AuditoriaItem, DocumentoFinanceiro, LancamentoERP


class AprovacaoFinanceiraCEOTests(TestCase):
    def setUp(self):
        configurar_aprovadores(self)
        self.ceo = User.objects.create_user('ceo_premium')
        self.operador = User.objects.create_user('financeiro-operador')
        PerfilUsuario.objects.create(usuario=self.operador, perfil='financeiro')
        self.operador.groups.add(Group.objects.create(name='Financeiro_Aprovador'))
        self.client.force_login(self.operador)
        self.doc = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='CEO-1', descricao='Material',
            valor=150, status='aprovado_lancamento', centro_custo='ADM',
        )
        for item, _ in AuditoriaItem.ITENS_CHECKLIST:
            AuditoriaItem.objects.create(documento=self.doc, item=item, status='ok')

    def enviar(self):
        return self.client.post(reverse('lancar_erp', args=[self.doc.pk]), {
            'descricao': 'Material de escritório', 'tipo': 'debito',
            'competencia': date.today().replace(day=1).isoformat(), 'centro_custo': 'ADM',
        })

    def test_envio_cria_aprovacao_nominal_e_operador_nao_decide(self):
        self.assertEqual(self.enviar().status_code, 302)
        lancamento = LancamentoERP.objects.get(documento=self.doc)
        aprovacao = AprovacaoRegistro.objects.get(modulo='financeiro', object_id=lancamento.pk)
        self.assertEqual(aprovacao.destinatario, self.ceo)
        self.assertEqual(aprovacao.nivel, 2)
        self.assertEqual(aprovacao.solicitado_por, self.operador)
        self.assertTrue(Notificacao.objects.filter(destinatario=self.ceo, modulo='financeiro', tipo='gateway').exists())
        url = reverse('validar_lancamento', args=[lancamento.pk])
        self.assertNotContains(self.client.get(url), 'value="validar"')
        for acao in ('validar', 'rejeitar'):
            # A decisão só encontra registros atribuídos ao usuário conectado.
            self.assertEqual(self.client.post(url, {'acao': acao, 'motivo_rejeicao': 'Teste'}).status_code, 404)
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.status, 'em_validacao')
        self.client.force_login(self.ceo)
        self.assertEqual(self.client.post(url, {'acao': 'validar'}).status_code, 302)
        lancamento.refresh_from_db()
        aprovacao.refresh_from_db()
        self.doc.refresh_from_db()
        self.assertEqual(lancamento.status, 'finalizado')
        self.assertEqual(lancamento.validado_por, self.ceo)
        self.assertIsNotNone(lancamento.finalizado_em)
        self.assertEqual(self.doc.status, 'arquivado')
        self.assertEqual(aprovacao.status, 'aprovado')
        self.assertEqual(aprovacao.aprovado_por, self.ceo)
        self.assertEqual(AprovacaoRegistro.objects.filter(object_id=lancamento.pk, modulo='financeiro').count(), 1)
        self.assertEqual(self.client.get(reverse('painel_financeiro')).context['total_lancado_mes'], 150)

    def test_rejeicao_central_reabre_documento_e_preserva_motivo(self):
        self.enviar()
        lancamento = LancamentoERP.objects.get(documento=self.doc)
        aprovacao = AprovacaoRegistro.objects.get(modulo='financeiro', object_id=lancamento.pk)
        self.client.force_login(self.ceo)
        response = self.client.post(reverse('rejeitar_registro', args=[aprovacao.pk]), {
            'motivo_rejeicao': 'Corrigir centro de custo',
        })
        self.assertEqual(response.status_code, 302)
        lancamento.refresh_from_db()
        self.doc.refresh_from_db()
        self.assertEqual(lancamento.status, 'rejeitado')
        self.assertEqual(lancamento.motivo_rejeicao, 'Corrigir centro de custo')
        self.assertEqual(self.doc.status, 'aprovado_lancamento')

    def test_sem_ceo_ativo_envio_e_atomico(self):
        self.ceo.is_active = False
        self.ceo.save(update_fields=['is_active'])
        self.assertEqual(self.enviar().status_code, 200)
        self.assertFalse(LancamentoERP.objects.exists())
        self.assertFalse(AprovacaoRegistro.objects.exists())
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'aprovado_lancamento')

    def test_cancelamento_retira_aprovacao_da_fila_sem_decisao_falsa(self):
        self.enviar()
        aprovacao = AprovacaoRegistro.objects.get(modulo='financeiro')
        response = self.client.post(reverse('cancelar_documento', args=[self.doc.pk]), {'motivo': 'Documento duplicado'})
        self.assertEqual(response.status_code, 302)
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'cancelado')
        self.assertIsNone(aprovacao.aprovado_por)
        self.client.force_login(self.ceo)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 404)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'cancelado')


class MigracaoFinanceiraCEOTests(TestCase):
    """Testa a lógica do backfill histórico contra o schema completo do runner."""

    def setUp(self):
        configurar_aprovadores(self)
        self.ceo = User.objects.create_user('ceo_premium')
        self.doc = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='LEGADO-CEO', descricao='Legado', valor=10, status='lancado',
        )
        self.lancamento = LancamentoERP.objects.create(
            documento=self.doc, descricao='Lançamento legado', tipo='debito', valor=10,
            centro_custo='ADM', competencia=date.today(), status='em_validacao',
        )
        self.migracao = import_module('financeiro.migrations.0012_lancamentos_pendentes_ceo')
        # A função histórica recebe modelos sem os métodos atuais, mas com as
        # colunas obrigatórias que já existem no banco de testes migrado.
        self.apps = MigrationLoader(connection).project_state().apps

    def migrar(self):
        self.migracao.encaminhar_lancamentos_pendentes(self.apps, SimpleNamespace(connection=connection))

    def test_backfill_e_idempotente_e_preserva_lancamento(self):
        self.migrar()
        self.migrar()
        aprovacao = AprovacaoRegistro.objects.get(modulo='financeiro')
        self.assertEqual(aprovacao.destinatario, self.ceo)
        self.assertEqual(aprovacao.object_id, self.lancamento.pk)
        self.assertEqual(aprovacao.nivel, 2)
        self.assertEqual(Notificacao.objects.filter(tipo='gateway').count(), 1)
        self.lancamento.refresh_from_db()
        self.assertEqual(self.lancamento.status, 'em_validacao')

    def test_backfill_nao_duplica_fila_existente(self):
        aprovacao = AprovacaoRegistro.criar_para(objeto=self.lancamento, titulo='Existente', modulo='financeiro')
        self.migrar()
        self.assertEqual(AprovacaoRegistro.objects.get(modulo='financeiro').pk, aprovacao.pk)

    def test_backfill_sem_ceo_nao_cria_aprovacao_sem_responsavel(self):
        self.ceo.delete()
        with self.assertRaises(RuntimeError):
            self.migrar()
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_documento_cancelado_nao_volta_para_aprovacao(self):
        self.doc.status = 'cancelado'
        self.doc.save(update_fields=['status'])
        self.migrar()
        self.assertFalse(AprovacaoRegistro.objects.exists())
