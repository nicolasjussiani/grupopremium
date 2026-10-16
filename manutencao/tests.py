from django.test import override_settings
from core.approval_test_utils import configurar_aprovadores
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import AprovacaoRegistro, PerfilUsuario
from manutencao.models import Ativo, RegistroManutencao


@override_settings(APROVADOR_OPERACIONAL_USERNAME='ceo_premium', APROVADOR_PAGAMENTOS_USERNAME='luiz_teste')
class AprovacaoManutencaoCEOTests(TestCase):
    def setUp(self):
        configurar_aprovadores(self)
        self.ceo = User.objects.create_user('ceo_premium')
        self.operador = User.objects.create_user('operador-manutencao')
        PerfilUsuario.objects.create(usuario=self.operador, perfil='sesmet')
        self.client.force_login(self.operador)
        self.ativo = Ativo.objects.create(
            numero_patrimonio='CEO-PAT-1', nome='Empilhadeira', unidade_atual='Matriz', status='ativo',
        )

    def abrir(self, **dados):
        return self.client.post(reverse('nova_manutencao'), {
            'ativo': self.ativo.pk, 'unidade_origem': 'Matriz',
            'motivo': 'Revisão', 'data_inicio': date.today().isoformat(),
            **dados,
        })

    def abrir_e_aprovar(self, **dados):
        self.assertEqual(self.abrir(**dados).status_code, 302)
        manutencao = RegistroManutencao.objects.get(ativo=self.ativo)
        aprovacao = AprovacaoRegistro.objects.get(modulo='manutencao', object_id=manutencao.pk)
        self.client.force_login(self.ceo)
        self.assertEqual(self.client.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 302)
        self.client.force_login(self.operador)
        return manutencao

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

    def test_chamado_concluido_nao_reabre_nem_libera_ativo_em_novo_reparo(self):
        antiga = self.abrir_e_aprovar()
        url = reverse('concluir_manutencao', args=[antiga.pk])
        self.client.post(url, {'status': 'concluida', 'obs': 'Reparo encerrado'})
        antiga.refresh_from_db()
        atualizado_em = antiga.atualizado_em
        data_conclusao = antiga.data_conclusao
        self.assertEqual(self.abrir(motivo='Novo defeito').status_code, 302)
        nova = RegistroManutencao.objects.exclude(pk=antiga.pk).get()

        for status in ('concluida', 'andamento', 'cancelada'):
            with self.subTest(status=status):
                response = self.client.post(url, {'status': status, 'obs': 'POST antigo'})
                self.assertRedirects(response, reverse('lista_manutencoes'))
                antiga.refresh_from_db()
                nova.refresh_from_db()
                self.ativo.refresh_from_db()
                self.assertEqual(antiga.status, 'concluida')
                self.assertEqual(antiga.obs, 'Reparo encerrado')
                self.assertEqual(antiga.atualizado_em, atualizado_em)
                self.assertEqual(antiga.data_conclusao, data_conclusao)
                self.assertEqual(nova.status, 'aguardando_aprovacao')
                self.assertEqual(self.ativo.status, 'manutencao')
        self.assertRedirects(self.client.get(url), reverse('lista_manutencoes'))

    def test_conclusao_preserva_fornecedor_ausente_e_formulario_permite_editar(self):
        manutencao = self.abrir_e_aprovar(fornecedor_servico='Oficina original')
        url = reverse('concluir_manutencao', args=[manutencao.pk])
        response = self.client.get(url)
        self.assertContains(response, 'name="fornecedor_servico"')
        self.assertContains(response, 'value="Oficina original"')
        self.client.post(url, {'status': 'andamento', 'fornecedor_servico': 'Oficina atualizada'})
        manutencao.refresh_from_db()
        self.assertEqual(manutencao.fornecedor_servico, 'Oficina atualizada')
        self.client.post(url, {'status': 'concluida'})
        manutencao.refresh_from_db()
        self.assertEqual(manutencao.status, 'concluida')
        self.assertEqual(manutencao.fornecedor_servico, 'Oficina atualizada')

    def test_conclusao_nao_libera_ativo_com_outro_chamado_aberto_legado(self):
        manutencao = self.abrir_e_aprovar()
        outro = RegistroManutencao.objects.create(
            ativo=self.ativo, unidade_origem='Filial', motivo='Outro defeito',
            data_inicio=date.today(), status='andamento',
        )
        self.client.post(reverse('concluir_manutencao', args=[manutencao.pk]), {
            'status': 'concluida', 'unidade_retorno': 'Outra unidade',
        })
        manutencao.refresh_from_db()
        outro.refresh_from_db()
        self.ativo.refresh_from_db()
        self.assertEqual(manutencao.status, 'concluida')
        self.assertEqual(outro.status, 'andamento')
        self.assertEqual(self.ativo.status, 'manutencao')
        self.assertEqual(self.ativo.unidade_atual, 'Matriz')

    def test_conclusao_nao_reativa_ativo_baixado(self):
        manutencao = self.abrir_e_aprovar()
        Ativo.objects.filter(pk=self.ativo.pk).update(status='inativo')
        self.client.post(reverse('concluir_manutencao', args=[manutencao.pk]), {'status': 'concluida'})
        manutencao.refresh_from_db()
        self.ativo.refresh_from_db()
        self.assertEqual(manutencao.status, 'concluida')
        self.assertEqual(self.ativo.status, 'inativo')

    def test_edicao_do_ativo_nao_disponibiliza_equipamento_com_chamado_aberto(self):
        self.abrir_e_aprovar()
        response = self.client.post(reverse('editar_ativo', args=[self.ativo.pk]), {
            'numero_patrimonio': self.ativo.numero_patrimonio,
            'nome': self.ativo.nome, 'unidade_atual': 'Matriz', 'status': 'ativo',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Encerre os chamados de manutenção')
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, 'manutencao')

    def test_ativo_legado_disponivel_com_chamado_aberto_nao_permite_duplicar(self):
        self.abrir_e_aprovar()
        Ativo.objects.filter(pk=self.ativo.pk).update(status='ativo')
        response = self.abrir(motivo='Chamado duplicado')
        self.assertRedirects(response, reverse('nova_manutencao'))
        self.assertEqual(RegistroManutencao.objects.filter(ativo=self.ativo).count(), 1)
        self.assertEqual(AprovacaoRegistro.objects.filter(modulo='manutencao').count(), 1)
