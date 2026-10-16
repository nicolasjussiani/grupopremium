from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from administrativo.models import DemandaAdministrativa
from core.models import AprovacaoRegistro, Notificacao
from core.views_aprovacao import _aprovacoes_do_usuario


@override_settings(APROVADOR_OPERACIONAL_USERNAME='thiago_teste', APROVADOR_PAGAMENTOS_USERNAME='luiz_teste')
class CentralApprovalTests(TestCase):
    def setUp(self):
        self.aprovador = User.objects.create_user('thiago_teste')
        self.gestor = User.objects.create_superuser('outro-admin')
        self.demanda = DemandaAdministrativa.objects.create(
            tipo='apoio_operacional', titulo='Compra de cadeiras', descricao='Reposição',
            requisitante='Gestor', status='recebida',
        )

    def criar(self, **kwargs):
        return AprovacaoRegistro.objects.create(
            content_type=ContentType.objects.get_for_model(self.demanda),
            object_id=self.demanda.pk, titulo='Analisar demanda', **kwargs,
        )

    def test_todos_modulos_encaminham_diretamente_ao_aprovador_operacional(self):
        for modulo, _ in AprovacaoRegistro.MODULOS:
            with self.subTest(modulo=modulo):
                aprovacao = self.criar(modulo=modulo, nivel=1, destinatario=self.gestor)
                self.assertEqual(aprovacao.destinatario, self.aprovador)
                self.assertEqual(aprovacao.nivel, 2)
                aviso = Notificacao.objects.get(
                    url_acao=reverse('detalhe_aprovacao_mobile', args=[aprovacao.pk]),
                )
                self.assertEqual(aviso.destinatario, self.aprovador)
                self.assertEqual(aviso.modulo, modulo)
        self.assertFalse(Notificacao.objects.filter(destinatario=self.gestor).exists())

    def test_nao_permite_reatribuir_pendencia_por_save(self):
        aprovacao = self.criar()
        aprovacao.destinatario = self.gestor
        aprovacao.nivel = 1
        aprovacao.save(update_fields=['destinatario', 'nivel'])
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.destinatario, self.aprovador)
        self.assertEqual(aprovacao.nivel, 2)
        self.assertEqual(Notificacao.objects.count(), 1)

    def test_fila_legada_exige_reatribuicao_antes_de_permitir_decisao(self):
        aprovacao = self.criar(modulo='administrativo')
        # Simula uma pendência anterior à migração, inclusive sem destinatário.
        for destinatario in (self.gestor, None):
            AprovacaoRegistro.objects.filter(pk=aprovacao.pk).update(destinatario=destinatario, nivel=1)
            self.assertFalse(_aprovacoes_do_usuario(self.aprovador).filter(pk=aprovacao.pk).exists())
            self.assertFalse(_aprovacoes_do_usuario(self.gestor).filter(pk=aprovacao.pk).exists())
            self.client.force_login(self.gestor)
            for view in ('detalhe_aprovacao', 'detalhe_aprovacao_mobile'):
                self.assertEqual(self.client.get(reverse(view, args=[aprovacao.pk])).status_code, 404)
            for view in ('aprovar_registro', 'rejeitar_registro'):
                self.assertEqual(self.client.post(
                    reverse(view, args=[aprovacao.pk]), {'motivo_rejeicao': 'Teste'},
                ).status_code, 404)
            self.assertEqual(self.client.get(reverse('aprovacoes_count_api')).json()['total'], 0)
            self.assertEqual(self.client.get(reverse('status_mobile')).json()['pendentes'], 0)
        AprovacaoRegistro.objects.filter(pk=aprovacao.pk).update(destinatario=self.aprovador)
        self.client.force_login(self.aprovador)
        self.assertEqual(self.client.get(reverse('status_mobile')).json()['pendentes'], 1)

    def test_historico_conserva_responsavel_original(self):
        aprovacao = self.criar(
            modulo='administrativo', status='aprovado', destinatario=self.gestor,
            aprovado_por=self.gestor, nivel=1,
        )
        aprovacao.comentario = 'Decisão anterior'
        aprovacao.save()
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.destinatario, self.gestor)
        self.assertEqual(aprovacao.aprovado_por, self.gestor)
        self.assertEqual(aprovacao.nivel, 1)
        self.assertTrue(_aprovacoes_do_usuario(self.gestor).filter(pk=aprovacao.pk).exists())
        self.assertFalse(Notificacao.objects.exists())

    def test_aprovador_operacional_inativo_ou_ausente_nao_cria_fila_sem_responsavel(self):
        self.aprovador.is_active = False
        self.aprovador.save(update_fields=['is_active'])
        with self.assertRaisesMessage(ValidationError, 'operacional'):
            self.criar()
        self.aprovador.delete()
        with self.assertRaisesMessage(ValidationError, 'operacional'):
            self.criar()
        self.assertFalse(AprovacaoRegistro.objects.exists())
        self.assertFalse(Notificacao.objects.exists())

    @patch('core.signals.enviar_mensagem_telegram')
    def test_aviso_telegram_usa_canal_operacional(self, enviar):
        with self.captureOnCommitCallbacks(execute=True):
            self.criar(modulo='admissional')
        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.args[0], 'aprovacoes_operacionais')

    def test_callback_invalido_preserva_pendencia(self):
        aprovacao = self.criar(modulo='administrativo')
        self.client.force_login(self.aprovador)
        with patch('core.views_aprovacao._executar_callback_aprovacao', side_effect=ValidationError('Estado inválido')):
            response = self.client.post(reverse('aprovar_registro', args=[aprovacao.pk]))
        self.assertEqual(response.status_code, 400)
        aprovacao.refresh_from_db()
        self.assertEqual(aprovacao.status, 'pendente')
        self.assertIsNone(aprovacao.aprovado_por)
        self.assertIsNone(aprovacao.decidido_em)

    def test_aviso_de_titulo_longo_cabe_no_limite_do_banco(self):
        aprovacao = AprovacaoRegistro.criar_para(
            objeto=self.demanda, titulo='A' * 255, modulo='administrativo',
        )
        aviso = Notificacao.objects.get(url_acao=reverse('detalhe_aprovacao_mobile', args=[aprovacao.pk]))
        self.assertEqual(aviso.titulo, 'A' * 200)
        self.assertEqual(aprovacao.titulo, 'A' * 255)

    def test_aprovador_operacional_decide_requisicao_legada_sem_etapa_adriana(self):
        from compras.models import RequisicaoCompra
        rc = RequisicaoCompra.objects.create(
            solicitante='Equipe', unidade_destino='Matriz', justificativa='Legado',
            status='aguardando_adriana',
        )
        aprovacao = AprovacaoRegistro.criar_para(objeto=rc, titulo='RC legada', modulo='compras')
        AprovacaoRegistro.objects.filter(pk=aprovacao.pk).update(destinatario=self.gestor, nivel=1)
        self.client.force_login(self.aprovador)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 404)
        AprovacaoRegistro.objects.filter(pk=aprovacao.pk).update(destinatario=self.aprovador)
        response = self.client.post(reverse('aprovar_registro', args=[aprovacao.pk]))
        self.assertEqual(response.status_code, 302)
        aprovacao.refresh_from_db()
        rc.refresh_from_db()
        self.assertEqual(aprovacao.status, 'aprovado')
        self.assertEqual(aprovacao.destinatario, self.aprovador)
        self.assertEqual(aprovacao.nivel, 2)
        self.assertEqual(rc.status, 'aprovada')
        self.assertEqual(AprovacaoRegistro.objects.count(), 1)
