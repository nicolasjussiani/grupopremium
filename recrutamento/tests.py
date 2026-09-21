from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import LogAtividade, Notificacao, PerfilUsuario
from recrutamento.models import Candidato, HistoricoVaga, Vaga


class GestaoVagaTests(TestCase):
    def test_repetir_exclusao_redireciona_sem_duplicar_historico_ou_notificacao(self):
        url = reverse('excluir_vaga', args=[self.vaga.pk])
        dados = {'motivo': 'outros', 'justificativa': 'Vaga cadastrada para teste.'}
        self.assertRedirects(self.client.post(url, dados), reverse('lista_vagas'))
        totais = (HistoricoVaga.objects.count(), LogAtividade.objects.count(), Notificacao.objects.count())
        for _ in range(3):
            response = self.client.post(url, dados, follow=True)
            self.assertContains(response, 'Esta vaga já não está disponível')
            self.assertEqual(response.redirect_chain, [(reverse('lista_vagas'), 302)])
        self.assertEqual(
            (HistoricoVaga.objects.count(), LogAtividade.objects.count(), Notificacao.objects.count()),
            totais,
        )
        self.assertRedirects(self.client.get(url), reverse('lista_vagas'))

    def setUp(self):
        self.usuario = User.objects.create_user(
            'rh-vagas', password='senha-forte-123', first_name='Pessoa', last_name='RH'
        )
        PerfilUsuario.objects.create(usuario=self.usuario, perfil='rh')
        self.client.force_login(self.usuario)
        self.vaga = Vaga.objects.create(
            nome_vaga='Analista de Teste',
            quantidade_colaboradores=1,
            cidade='Santos',
            unidade='Matriz',
            perfil_desejado='Perfil inicial',
            atividades='Atividades iniciais',
            horario_trabalho='08h às 17h',
            tipo_contratacao='clt',
            valor_salario='2500.00',
            previsao_inicio=date(2026, 10, 1),
            motivo_solicitacao='Aumento de quadro',
            gestor_responsavel='Gestor Responsável',
            gestor_usuario=self.usuario,
            status='em_selecao',
        )

    def dados_edicao(self, **alteracoes):
        dados = {
            'nome_vaga': self.vaga.nome_vaga,
            'quantidade_colaboradores': '1',
            'cidade': self.vaga.cidade,
            'unidade': self.vaga.unidade,
            'perfil_desejado': self.vaga.perfil_desejado,
            'atividades': self.vaga.atividades,
            'horario_trabalho': self.vaga.horario_trabalho,
            'tipo_contratacao': self.vaga.tipo_contratacao,
            'valor_salario': '2500.00',
            'previsao_inicio': '2026-10-01',
            'descricao_experiencia': '',
            'motivo_solicitacao': self.vaga.motivo_solicitacao,
            'gestor_responsavel': self.vaga.gestor_responsavel,
            'status': self.vaga.status,
            'observacoes': '',
            'motivo_alteracao': 'erro_digitacao',
            'justificativa_alteracao': 'O nome da vaga foi digitado incorretamente.',
        }
        dados.update(alteracoes)
        return dados

    def test_edita_vaga_e_registra_dados_anteriores(self):
        response = self.client.post(
            reverse('editar_vaga', args=[self.vaga.pk]),
            self.dados_edicao(nome_vaga='Analista de Qualidade'),
        )

        self.assertRedirects(response, reverse('detalhe_vaga', args=[self.vaga.pk]))
        self.vaga.refresh_from_db()
        self.assertEqual(self.vaga.nome_vaga, 'Analista de Qualidade')
        historico = HistoricoVaga.objects.get()
        self.assertEqual(historico.acao, 'edicao')
        self.assertEqual(historico.motivo, 'erro_digitacao')
        self.assertEqual(historico.dados_anteriores['nome_vaga'], 'Analista de Teste')
        self.assertEqual(historico.dados_novos['nome_vaga'], 'Analista de Qualidade')
        self.assertEqual(historico.realizado_por, self.usuario)

    def test_edicao_exige_motivo_e_justificativa(self):
        response = self.client.post(
            reverse('editar_vaga', args=[self.vaga.pk]),
            self.dados_edicao(
                nome_vaga='Nome que não deve ser salvo',
                motivo_alteracao='',
                justificativa_alteracao='',
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.vaga.refresh_from_db()
        self.assertEqual(self.vaga.nome_vaga, 'Analista de Teste')
        self.assertFalse(HistoricoVaga.objects.exists())

    def test_exclui_vaga_com_candidatos_e_preserva_historico(self):
        Candidato.objects.create(
            vaga=self.vaga,
            nome='Candidato Teste',
            email='candidato@example.com',
            telefone='11999999999',
            cidade='Santos',
            cpf_cnpj='123.456.789-00',
        )
        vaga_id = self.vaga.pk

        response = self.client.post(
            reverse('excluir_vaga', args=[vaga_id]),
            {
                'motivo': 'acidente',
                'justificativa': 'A abertura ocorreu devido a uma ocorrência registrada por engano.',
            },
        )

        self.assertRedirects(response, reverse('lista_vagas'))
        self.assertFalse(Vaga.objects.filter(pk=vaga_id).exists())
        self.assertFalse(Candidato.objects.exists())
        historico = HistoricoVaga.objects.get()
        self.assertIsNone(historico.vaga_id)
        self.assertEqual(historico.vaga_id_original, vaga_id)
        self.assertEqual(historico.nome_vaga, 'Analista de Teste')
        self.assertEqual(historico.candidatos_afetados, 1)

    def test_exclusao_invalida_nao_remove_vaga(self):
        response = self.client.post(
            reverse('excluir_vaga', args=[self.vaga.pk]),
            {'motivo': '', 'justificativa': 'x'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Vaga.objects.filter(pk=self.vaga.pk).exists())
        self.assertFalse(HistoricoVaga.objects.exists())

    def test_lista_exibe_tabela_de_historico(self):
        HistoricoVaga.objects.create(
            vaga=self.vaga,
            vaga_id_original=self.vaga.pk,
            nome_vaga=self.vaga.nome_vaga,
            acao='edicao',
            motivo='outros',
            justificativa='Ajuste solicitado pelo responsável da unidade.',
            dados_anteriores={},
            dados_novos={},
            realizado_por=self.usuario,
        )

        response = self.client.get(reverse('lista_vagas'))

        self.assertContains(response, 'Histórico de alterações e exclusões')
        self.assertContains(response, 'Ajuste solicitado pelo responsável')
        self.assertContains(response, reverse('editar_vaga', args=[self.vaga.pk]))
        self.assertContains(response, reverse('excluir_vaga', args=[self.vaga.pk]))


class PermissaoGestaoVagaTests(TestCase):
    def test_operacional_nao_edita_nem_exclui_vaga(self):
        usuario = User.objects.create_user('operacional-vagas', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=usuario, perfil='operacional')
        vaga = Vaga.objects.create(
            nome_vaga='Vaga Protegida', quantidade_colaboradores=1,
            cidade='Santos', unidade='Matriz', perfil_desejado='Perfil',
            atividades='Atividades', horario_trabalho='08h às 17h',
            tipo_contratacao='clt', valor_salario='2000.00',
            previsao_inicio=date(2026, 10, 1), motivo_solicitacao='Teste',
            gestor_responsavel='Gestor', status='em_selecao',
        )
        self.client.force_login(usuario)

        self.assertRedirects(
            self.client.get(reverse('editar_vaga', args=[vaga.pk])), reverse('dashboard')
        )
        self.assertRedirects(
            self.client.get(reverse('excluir_vaga', args=[vaga.pk])), reverse('dashboard')
        )
