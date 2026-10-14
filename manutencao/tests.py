from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import AprovacaoRegistro, PerfilUsuario
from manutencao.models import Ativo, RegistroManutencao


class AprovacaoManutencaoCEOTests(TestCase):
    def setUp(self):
        self.ceo = User.objects.create_user('ceo_premium')
        self.operador = User.objects.create_user('operador-manutencao')
        PerfilUsuario.objects.create(usuario=self.operador, perfil='sesmet')
        self.client.force_login(self.operador)
        self.ativo = Ativo.objects.create(
            numero_patrimonio='CEO-PAT-1', nome='Empilhadeira', unidade_atual='Matriz', status='ativo',
        )

    def abrir(self):
        return self.client.post(reverse('nova_manutencao'), {
            'ativo': self.ativo.pk, 'unidade_origem': 'Matriz',
            'motivo': 'Revisão', 'data_inicio': date.today().isoformat(),
        })

    def test_aguarda_ceo_antes_de_iniciar_ou_concluir(self):
        self.assertEqual(self.abrir().status_code, 302)
        manutencao = RegistroManutencao.objects.get(ativo=self.ativo)
        aprovacao = AprovacaoRegistro.objects.get(modulo='manutencao', object_id=manutencao.pk)
        self.assertEqual(aprovacao.destinatario, self.ceo)
        for status in ('andamento', 'concluida', 'cancelada'):
            self.client.post(reverse('concluir_manutencao', args=[manutencao.pk]), {'status': status})
            manutencao.refresh_from_db()
            self.assertEqual(manutencao.status, 'aguardando_aprovacao')
        self.client.force_login(self.ceo)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 302)
        self.client.force_login(self.operador)
        self.client.post(reverse('concluir_manutencao', args=[manutencao.pk]), {'status': 'concluida'})
        manutencao.refresh_from_db()
        self.ativo.refresh_from_db()
        self.assertEqual(manutencao.status, 'concluida')
        self.assertEqual(self.ativo.status, 'ativo')

    def test_sem_ceo_ativo_abertura_nao_altera_ativo(self):
        self.ceo.is_active = False
        self.ceo.save(update_fields=['is_active'])
        self.assertEqual(self.abrir().status_code, 302)
        self.assertFalse(RegistroManutencao.objects.exists())
        self.assertFalse(AprovacaoRegistro.objects.exists())
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, 'ativo')

    def test_rejeicao_nao_pode_ser_contornada_pela_conclusao(self):
        self.abrir()
        manutencao = RegistroManutencao.objects.get()
        aprovacao = AprovacaoRegistro.objects.get(modulo='manutencao')
        self.client.force_login(self.ceo)
        self.client.post(reverse('rejeitar_registro', args=[aprovacao.pk]), {'motivo_rejeicao': 'Sem necessidade'})
        self.client.force_login(self.operador)
        self.client.post(reverse('concluir_manutencao', args=[manutencao.pk]), {'status': 'concluida'})
        manutencao.refresh_from_db()
        self.assertEqual(manutencao.status, 'cancelada')
