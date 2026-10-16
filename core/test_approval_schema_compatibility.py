from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from administrativo.models import DemandaAdministrativa
from core.models import AprovacaoRegistro
from core.payment_approvals import (
    exigir_aprovacao_pagamento, sincronizar_aprovacao_pagamento,
    situacao_aprovacao_pagamento, snapshot_pagamento,
)
from core.views_aprovacao import _aprovacoes_do_usuario
from financeiro.models import DocumentoFinanceiro


@override_settings(
    APROVADOR_PAGAMENTOS_USERNAME='luiz_compatibilidade',
    APROVADOR_OPERACIONAL_USERNAME='thiago_compatibilidade',
)
class ApprovalSchemaCompatibilityTests(TestCase):
    """A versão antiga pode gravar durante a expansão, sem ganhar novos poderes."""

    @classmethod
    def setUpTestData(cls):
        estado_anterior = MigrationLoader(connection).project_state([
            ('core', '0022_centralizar_aprovacoes_ceo'),
        ])
        cls.AprovacaoAnterior = estado_anterior.apps.get_model('core', 'AprovacaoRegistro')
        cls.luiz = User.objects.create_user('luiz_compatibilidade')
        cls.thiago = User.objects.create_user('thiago_compatibilidade')
        cls.ceo = User.objects.create_superuser('ceo_premium')
        cls.demanda = DemandaAdministrativa.objects.create(
            tipo='apoio_operacional', titulo='Operação legada', descricao='Teste de expansão',
            requisitante='Equipe',
        )
        cls.documento = DocumentoFinanceiro.objects.create(
            tipo='boleto', numero_documento='COMPATIBILIDADE', descricao='Fornecedor de teste',
            valor='100.00', situacao_pagamento='a_pagar', status='lancado',
        )

    def setUp(self):
        telegram = patch('core.signals.enviar_mensagem_telegram')
        telegram.start()
        self.addCleanup(telegram.stop)

    def inserir_com_versao_anterior(self, objeto, **campos):
        dados = {
            'content_type_id': ContentType.objects.get_for_model(objeto).pk,
            'object_id': objeto.pk, 'titulo': 'Solicitação pela versão anterior',
            'modulo': 'financeiro' if isinstance(objeto, DocumentoFinanceiro) else 'administrativo',
            'destinatario_id': self.ceo.pk, 'nivel': 2,
        }
        dados.update(campos)
        return self.AprovacaoAnterior.objects.create(**dados)

    def test_insert_do_modelo_anterior_funciona_sem_conhecer_as_novas_colunas(self):
        campos_antigos = {campo.name for campo in self.AprovacaoAnterior._meta.fields}
        self.assertNotIn('finalidade', campos_antigos)
        self.assertNotIn('dados_aprovacao', campos_antigos)
        # O schema real já contém a migração 0023. O ORM histórico omite as duas
        # colunas no INSERT, reproduzindo a gravação feita pelo main anterior.
        for objeto in (self.demanda, self.documento):
            with self.subTest(modelo=objeto._meta.label_lower):
                antiga = self.inserir_com_versao_anterior(objeto)
                atual = AprovacaoRegistro.objects.get(pk=antiga.pk)
                self.assertIsNone(atual.finalidade)
                self.assertIsNone(atual.dados_aprovacao)
                self.assertEqual(atual.destinatario, self.ceo)
                antiga.comentario = 'Atualização ainda pela versão anterior'
                antiga.save(update_fields=['comentario'])
                atual.refresh_from_db()
                self.assertEqual(atual.comentario, antiga.comentario)
                self.assertIsNone(atual.finalidade)
                self.assertIsNone(atual.dados_aprovacao)

    def test_pendencias_sem_classificacao_nao_entram_nas_filas_nem_aceitam_decisao(self):
        registros = [
            self.inserir_com_versao_anterior(self.documento, destinatario_id=self.luiz.pk),
            self.inserir_com_versao_anterior(self.demanda, destinatario_id=self.thiago.pk),
        ]
        for usuario in (self.luiz, self.thiago, self.ceo):
            with self.subTest(username=usuario.username):
                self.assertFalse(_aprovacoes_do_usuario(usuario).filter(status='pendente').exists())
                self.client.force_login(usuario)
                for registro in registros:
                    for acao in ('aprovar_registro', 'rejeitar_registro'):
                        response = self.client.post(reverse(acao, args=[registro.pk]), {
                            'motivo_rejeicao': 'Tentativa sobre fila sem classificação',
                        })
                        self.assertEqual(response.status_code, 404)
        self.assertEqual(AprovacaoRegistro.objects.filter(status='pendente').count(), 2)

    def test_finalidade_ou_snapshot_nulos_nao_autorizam_baixa(self):
        antiga = self.inserir_com_versao_anterior(
            self.documento, status='aprovado', destinatario_id=self.luiz.pk,
            aprovado_por_id=self.luiz.pk, decidido_em=timezone.now(),
        )
        for finalidade, dados in (
            (None, None),
            (None, snapshot_pagamento(self.documento)),
            ('pagamento', None),
        ):
            with self.subTest(finalidade=finalidade, snapshot_nulo=dados is None):
                AprovacaoRegistro.objects.filter(pk=antiga.pk).update(
                    finalidade=finalidade, dados_aprovacao=dados,
                )
                with self.assertRaises(ValidationError):
                    exigir_aprovacao_pagamento(self.documento)
                self.assertEqual(situacao_aprovacao_pagamento(self.documento), 'nao_solicitado')

    def test_redistribuicao_converte_pendencias_nulas_e_preserva_historico(self):
        operacional = self.inserir_com_versao_anterior(self.demanda)
        pagamento = self.inserir_com_versao_anterior(self.documento)
        historico = self.inserir_com_versao_anterior(
            self.documento, status='aprovado', aprovado_por_id=self.ceo.pk,
            decidido_em=timezone.now(), comentario='Decisão anterior à implantação',
        )
        antes = AprovacaoRegistro.objects.filter(pk=historico.pk).values().get()
        call_command('redistribuir_aprovacoes', apply=True, stdout=StringIO())
        operacional_atual = AprovacaoRegistro.objects.get(pk=operacional.pk)
        pagamento_antigo = AprovacaoRegistro.objects.get(pk=pagamento.pk)
        self.assertEqual(operacional_atual.finalidade, 'operacional')
        self.assertEqual(operacional_atual.destinatario, self.thiago)
        self.assertEqual(pagamento_antigo.status, 'cancelado')
        self.assertIsNone(pagamento_antigo.finalidade)
        self.assertIsNone(pagamento_antigo.dados_aprovacao)
        novo = AprovacaoRegistro.objects.get(
            content_type=ContentType.objects.get_for_model(self.documento),
            object_id=self.documento.pk, status='pendente',
        )
        self.assertEqual(novo.finalidade, 'pagamento')
        self.assertEqual(novo.destinatario, self.luiz)
        self.assertEqual(novo.dados_aprovacao, snapshot_pagamento(self.documento))
        self.assertEqual(AprovacaoRegistro.objects.filter(pk=historico.pk).values().get(), antes)
        self.assertEqual(set(_aprovacoes_do_usuario(self.thiago).values_list('pk', flat=True)), {operacional.pk})
        self.assertEqual(set(_aprovacoes_do_usuario(self.luiz).values_list('pk', flat=True)), {novo.pk})
        depois = list(AprovacaoRegistro.objects.order_by('pk').values())
        call_command('redistribuir_aprovacoes', apply=True, stdout=StringIO())
        self.assertEqual(list(AprovacaoRegistro.objects.order_by('pk').values()), depois)

    def test_app_novo_mantem_defaults_classificacao_e_responsavel_obrigatorio(self):
        nova = AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(self.demanda),
            object_id=self.demanda.pk, titulo='App novo', finalidade=None,
            destinatario=self.luiz,
        )
        self.assertEqual(nova.finalidade, 'operacional')
        self.assertEqual(nova.destinatario, self.thiago)
        self.assertEqual(nova.dados_aprovacao, {})
        pagamento = sincronizar_aprovacao_pagamento(self.documento)
        self.assertEqual(pagamento.finalidade, 'pagamento')
        self.assertEqual(pagamento.destinatario, self.luiz)
        self.assertEqual(pagamento.dados_aprovacao, snapshot_pagamento(self.documento))
        quantidade = AprovacaoRegistro.objects.count()
        with override_settings(APROVADOR_OPERACIONAL_USERNAME=''):
            with self.assertRaises(ValidationError):
                AprovacaoRegistro.criar_para(self.demanda, 'Sem responsável')
        self.assertEqual(AprovacaoRegistro.objects.count(), quantidade)

    def test_salvar_historico_nulo_na_versao_nova_nao_reclassifica_decisao(self):
        antiga = self.inserir_com_versao_anterior(
            self.demanda, status='rejeitado', aprovado_por_id=self.ceo.pk,
            decidido_em=timezone.now(),
        )
        historico = AprovacaoRegistro.objects.get(pk=antiga.pk)
        historico.comentario = 'Anotação histórica'
        with override_settings(APROVADOR_OPERACIONAL_USERNAME=''):
            historico.save(update_fields=['comentario'])
        historico.refresh_from_db()
        self.assertIsNone(historico.finalidade)
        self.assertIsNone(historico.dados_aprovacao)
        self.assertEqual(historico.status, 'rejeitado')
        self.assertEqual(historico.aprovado_por, self.ceo)
        self.assertEqual(historico.destinatario, self.ceo)
