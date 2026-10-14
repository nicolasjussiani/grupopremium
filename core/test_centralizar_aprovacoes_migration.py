import importlib
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


class CentralizarAprovacoesMigrationTests(TestCase):
    """Exercita os modelos históricos e a transferência em SQLite de testes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migration = importlib.import_module(
            'core.migrations.0022_centralizar_aprovacoes_ceo',
        )
        executor = MigrationExecutor(connection)
        cls.apps = executor.loader.project_state([
            ('core', '0021_desativar_bloqueio_ip'),
            ('compras', '0012_pedido_com_itens'),
        ]).apps
        cls.Usuario = cls.apps.get_model('auth', 'User')
        cls.Aprovacao = cls.apps.get_model('core', 'AprovacaoRegistro')
        cls.Notificacao = cls.apps.get_model('core', 'Notificacao')
        cls.Log = cls.apps.get_model('core', 'LogAtividade')
        cls.Requisicao = cls.apps.get_model('compras', 'RequisicaoCompra')

    def setUp(self):
        self.outro = self.Usuario.objects.create(username='responsavel_anterior')
        ContentType = self.apps.get_model('contenttypes', 'ContentType')
        self.ct, _ = ContentType.objects.get_or_create(
            app_label='compras', model='requisicaocompra',
        )

    def executar(self):
        self.migration.centralizar_aprovacoes(
            self.apps, SimpleNamespace(connection=connection),
        )

    def criar_ceo(self, **kwargs):
        return self.Usuario.objects.create(username='ceo_premium', **kwargs)

    def aprovacao(self, **kwargs):
        valores = dict(
            content_type_id=self.ct.pk,
            object_id=999,
            titulo='Solicitação pendente',
            modulo='compras',
            destinatario_id=self.outro.pk,
            solicitado_por_id=self.outro.pk,
        )
        valores.update(kwargs)
        return self.Aprovacao.objects.create(**valores)

    def requisicao(self, **kwargs):
        valores = dict(
            solicitante='Solicitante',
            solicitante_usuario_id=self.outro.pk,
            unidade_destino='Unidade Premium',
            justificativa='Reposição',
            status='aguardando_adriana',
        )
        valores.update(kwargs)
        return self.Requisicao.objects.create(**valores)

    def aviso(self, aprovacao, **kwargs):
        valores = dict(
            destinatario_id=self.outro.pk,
            tipo='gateway',
            modulo=aprovacao.modulo,
            titulo=aprovacao.titulo,
            mensagem='Aguardando aprovação',
            url_acao=reverse('detalhe_aprovacao_mobile', args=[aprovacao.pk]),
        )
        valores.update(kwargs)
        return self.Notificacao.objects.create(**valores)

    def test_transfere_todos_modulos_niveis_e_sem_destinatario_com_auditoria(self):
        ceo = self.Usuario.objects.create(username='CEO_PREMIUM')
        registros = [
            self.aprovacao(modulo=modulo, nivel=nivel, destinatario_id=destinatario)
            for modulo, nivel, destinatario in (
                ('compras', 1, self.outro.pk),
                ('financeiro', 2, self.outro.pk),
                ('recrutamento', 1, None),
                ('sistema', 1, ceo.pk),
                ('manutencao', 1, self.outro.pk),
            )
        ]
        self.executar()
        for registro in registros:
            registro.refresh_from_db()
            self.assertEqual((registro.destinatario_id, registro.nivel, registro.status),
                             (ceo.pk, 2, 'pendente'))
            self.assertEqual(registro.solicitado_por_id, self.outro.pk)
            self.assertIsNone(registro.aprovado_por_id)
            self.assertIsNone(registro.decidido_em)
        self.assertEqual(self.Aprovacao.objects.count(), len(registros))
        self.assertEqual(self.Notificacao.objects.filter(destinatario_id=ceo.pk).count(), len(registros))
        self.assertEqual(self.Log.objects.count(), len(registros))
        log = self.Log.objects.get(url=reverse('detalhe_aprovacao_mobile', args=[registros[0].pk]))
        detalhes = json.loads(log.detalhes)
        self.assertIsNone(log.usuario_id)
        self.assertEqual(detalhes['destinatario_anterior_id'], self.outro.pk)
        self.assertEqual(detalhes['destinatario_anterior_username'], self.outro.username)
        self.assertEqual(detalhes['nivel_anterior'], 1)
        self.assertEqual(detalhes['destinatario_atual_id'], ceo.pk)

    def test_preserva_decisoes_cancelamentos_e_notificacoes_do_historico(self):
        self.criar_ceo()
        for status in ('aprovado', 'rejeitado', 'cancelado'):
            registro = self.aprovacao(
                status=status, nivel=1, aprovado_por_id=self.outro.pk,
                decidido_em=timezone.now(), comentario='Decisão original',
                motivo_rejeicao='Histórico preservado',
            )
            self.aviso(registro)
        antes = list(self.Aprovacao.objects.order_by('pk').values())
        avisos_antes = list(self.Notificacao.objects.order_by('pk').values())
        self.executar()
        self.assertEqual(antes, list(self.Aprovacao.objects.order_by('pk').values()))
        self.assertEqual(avisos_antes, list(self.Notificacao.objects.order_by('pk').values()))
        self.assertFalse(self.Log.objects.exists())

    def test_encerra_so_gateway_da_aprovacao_e_reutiliza_aviso_do_ceo(self):
        ceo = self.criar_ceo()
        registro = self.aprovacao()
        anterior = self.aviso(registro)
        desktop = self.aviso(registro, url_acao=reverse('detalhe_aprovacao', args=[registro.pk]))
        informativo = self.aviso(registro, tipo='info')
        outro_processo = self.aviso(registro, url_acao='/admissional/44/')
        aviso_ceo = self.aviso(registro, destinatario_id=ceo.pk, lida=True)
        self.executar()
        for aviso in (anterior, desktop, informativo, outro_processo, aviso_ceo):
            aviso.refresh_from_db()
        self.assertTrue(anterior.lida)
        self.assertTrue(desktop.lida)
        self.assertFalse(informativo.lida)
        self.assertFalse(outro_processo.lida)
        self.assertFalse(aviso_ceo.lida)
        self.assertEqual(self.Notificacao.objects.filter(destinatario_id=ceo.pk).count(), 1)

    def test_requisicoes_passam_ao_ceo_sem_colapsar_etapas_e_recupera_orfas(self):
        ceo = self.criar_ceo()
        requisicao = self.requisicao()
        primeira = self.aprovacao(object_id=requisicao.pk, nivel=1)
        segunda = self.aprovacao(object_id=requisicao.pk, nivel=2)
        orfas = [self.requisicao(status=status) for status in ('aguardando_adriana', 'aguardando_ceo')]
        concluida = self.requisicao(status='aprovada')
        self.executar()
        for item in (requisicao, *orfas):
            item.refresh_from_db()
            self.assertEqual(item.status, 'aguardando_ceo')
        concluida.refresh_from_db()
        self.assertEqual(concluida.status, 'aprovada')
        self.assertEqual(self.Aprovacao.objects.filter(object_id=requisicao.pk).count(), 2)
        self.assertEqual(set(self.Aprovacao.objects.filter(object_id=requisicao.pk).values_list('pk', flat=True)),
                         {primeira.pk, segunda.pk})
        for orfa in orfas:
            registro = self.Aprovacao.objects.get(content_type_id=self.ct.pk, object_id=orfa.pk)
            self.assertEqual((registro.nivel, registro.destinatario_id), (2, ceo.pk))
            self.assertEqual(registro.solicitado_por_id, self.outro.pk)
        self.assertFalse(self.Aprovacao.objects.filter(object_id=concluida.pk).exists())

    def test_execucao_repetida_nao_duplica_aprovacoes_notificacoes_ou_auditoria(self):
        ceo = self.criar_ceo()
        self.aprovacao()
        ja_centralizada = self.aprovacao(destinatario_id=ceo.pk, nivel=2)
        self.aviso(ja_centralizada, destinatario_id=ceo.pk, lida=True)
        self.requisicao()
        self.executar()
        antes = [list(modelo.objects.order_by('pk').values()) for modelo in (
            self.Aprovacao, self.Notificacao, self.Log, self.Requisicao,
        )]
        self.executar()
        depois = [list(modelo.objects.order_by('pk').values()) for modelo in (
            self.Aprovacao, self.Notificacao, self.Log, self.Requisicao,
        )]
        self.assertEqual(antes, depois)

    def test_base_nova_sem_ceo_e_sem_pendencias_passa(self):
        self.executar()
        self.assertFalse(self.Aprovacao.objects.exists())
        self.assertFalse(self.Notificacao.objects.exists())
        self.assertFalse(self.Log.objects.exists())

    def test_sem_ceo_ativo_ou_com_ceo_ambiguo_falha_sem_modificar_pendencias(self):
        registro = self.aprovacao()
        requisicao = self.requisicao()
        for situacao in ('ausente', 'inativo', 'ambiguo'):
            with self.subTest(situacao=situacao):
                if situacao == 'inativo':
                    ceo = self.criar_ceo(is_active=False)
                elif situacao == 'ambiguo':
                    ceo.is_active = True
                    ceo.save(update_fields=['is_active'])
                    self.Usuario.objects.create(username='CEO_PREMIUM')
                with self.assertRaisesRegex(RuntimeError, 'exatamente um usuário ativo'):
                    self.executar()
                registro.refresh_from_db()
                requisicao.refresh_from_db()
                self.assertEqual((registro.destinatario_id, registro.nivel), (self.outro.pk, 1))
                self.assertEqual(requisicao.status, 'aguardando_adriana')
                self.assertFalse(self.Notificacao.objects.exists())
                self.assertFalse(self.Log.objects.exists())

    def test_requisicao_orfa_sem_ceo_falha_antes_de_alterar_status(self):
        requisicao = self.requisicao()
        with self.assertRaisesRegex(RuntimeError, 'ceo_premium'):
            self.executar()
        requisicao.refresh_from_db()
        self.assertEqual(requisicao.status, 'aguardando_adriana')
        self.assertFalse(self.Aprovacao.objects.exists())

    def test_falha_durante_transferencia_reverte_todas_as_alteracoes(self):
        self.criar_ceo()
        registro = self.aprovacao()
        aviso = self.aviso(registro)
        with patch.object(self.migration.json, 'dumps', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaisesRegex(RuntimeError, 'Falha simulada'):
                self.executar()
        registro.refresh_from_db()
        aviso.refresh_from_db()
        self.assertEqual((registro.destinatario_id, registro.nivel), (self.outro.pk, 1))
        self.assertFalse(aviso.lida)
        self.assertEqual(self.Notificacao.objects.count(), 1)
        self.assertFalse(self.Log.objects.exists())
