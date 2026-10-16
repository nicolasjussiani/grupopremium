from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import AprovacaoRegistro
from manutencao.models import Ativo, RegistroManutencao


@override_settings(APROVADOR_OPERACIONAL_USERNAME='thiago_teste', APROVADOR_PAGAMENTOS_USERNAME='luiz_teste')
class MaintenanceApprovalIntegrityTests(TestCase):
    def setUp(self):
        self.aprovador = User.objects.create_user('thiago_teste')
        self.client.force_login(self.aprovador)
        self.ativo = Ativo.objects.create(
            numero_patrimonio='APPROVAL-01', nome='Lavadora',
            unidade_atual='Matriz', status='manutencao',
        )
        self.registro = self.criar_registro('aguardando_aprovacao')
        self.aprovacao = AprovacaoRegistro.criar_para(
            objeto=self.registro, titulo='Reparo da lavadora', modulo='manutencao',
        )

    def criar_registro(self, status):
        return RegistroManutencao.objects.create(
            ativo=self.ativo, unidade_origem='Matriz', motivo='Reparo',
            data_inicio=date.today(), status=status,
        )

    def rejeitar(self):
        return self.client.post(
            reverse('rejeitar_registro', args=[self.aprovacao.pk]),
            {'motivo_rejeicao': 'Orçamento não aprovado'},
        )

    def test_rejeicao_preserva_bloqueio_quando_existe_outro_chamado(self):
        for status in ('aguardando_aprovacao', 'aberta', 'andamento'):
            with self.subTest(status=status):
                outro = self.criar_registro(status)
                response = self.rejeitar()
                self.assertEqual(response.status_code, 302)
                self.registro.refresh_from_db()
                self.ativo.refresh_from_db()
                outro.refresh_from_db()
                self.assertEqual(self.registro.status, 'cancelada')
                self.assertEqual(self.ativo.status, 'manutencao')
                self.assertEqual(outro.status, status)
                outro.delete()
                RegistroManutencao.objects.filter(pk=self.registro.pk).update(
                    status='aguardando_aprovacao',
                )
                AprovacaoRegistro.objects.filter(pk=self.aprovacao.pk).update(
                    status='pendente', aprovado_por=None, decidido_em=None,
                )

    def test_rejeicao_nao_reativa_patrimonio_baixado(self):
        self.ativo.status = 'inativo'
        self.ativo.save(update_fields=['status'])
        self.assertEqual(self.rejeitar().status_code, 302)
        self.ativo.refresh_from_db()
        self.registro.refresh_from_db()
        self.assertEqual(self.ativo.status, 'inativo')
        self.assertEqual(self.registro.status, 'cancelada')

    def test_decisao_antiga_nao_reabre_nem_cancela_chamado_ja_concluido(self):
        self.registro.status = 'concluida'
        self.registro.data_conclusao = date.today()
        self.registro.save(update_fields=['status', 'data_conclusao'])
        self.ativo.status = 'ativo'
        self.ativo.save(update_fields=['status'])
        for action in ('aprovar_registro', 'rejeitar_registro'):
            with self.subTest(action=action):
                response = self.client.post(
                    reverse(action, args=[self.aprovacao.pk]),
                    {'motivo_rejeicao': 'Pedido antigo'},
                )
                self.assertEqual(response.status_code, 400)
                self.registro.refresh_from_db()
                self.ativo.refresh_from_db()
                self.aprovacao.refresh_from_db()
                self.assertEqual(self.registro.status, 'concluida')
                self.assertEqual(self.ativo.status, 'ativo')
                self.assertEqual(self.aprovacao.status, 'pendente')
                self.assertIsNone(self.aprovacao.aprovado_por)

    def test_aprovacao_preserva_indisponibilidade_do_ativo(self):
        self.ativo.status = 'ativo'
        self.ativo.save(update_fields=['status'])
        response = self.client.post(reverse('aprovar_registro', args=[self.aprovacao.pk]))
        self.assertEqual(response.status_code, 302)
        self.ativo.refresh_from_db()
        self.registro.refresh_from_db()
        self.assertEqual(self.ativo.status, 'manutencao')
        self.assertEqual(self.registro.status, 'aberta')

    def test_aprovacao_de_ativo_baixado_preserva_pendencia(self):
        self.ativo.status = 'inativo'
        self.ativo.save(update_fields=['status'])
        response = self.client.post(reverse('aprovar_registro', args=[self.aprovacao.pk]))
        self.assertEqual(response.status_code, 400)
        self.registro.refresh_from_db()
        self.aprovacao.refresh_from_db()
        self.assertEqual(self.registro.status, 'aguardando_aprovacao')
        self.assertEqual(self.aprovacao.status, 'pendente')
