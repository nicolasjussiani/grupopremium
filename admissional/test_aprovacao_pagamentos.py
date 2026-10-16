from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import AprovacaoRegistro
from core.payment_approvals import situacao_aprovacao_pagamento
from .models import Colaborador, PagamentoColaborador


@override_settings(APROVADOR_PAGAMENTOS_USERNAME='luiz_teste', APROVADOR_OPERACIONAL_USERNAME='thiago_teste')
class AprovacaoPagamentosFolhaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operador = User.objects.create_superuser('operador_folha_teste')
        cls.luiz = User.objects.create_user('luiz_teste')
        cls.thiago = User.objects.create_user('thiago_teste')
        cls.pessoa = Colaborador.objects.create(nome='Pessoa da folha', salario=3000, vale_transporte_semanal=100)

    def setUp(self):
        self.client.force_login(self.operador)
        self.hoje = timezone.localdate()
        self.dados = {
            'colaborador': self.pessoa.pk, 'tipo': 'salario',
            'competencia': self.hoje.replace(day=1).isoformat(),
            'competencia_fim': self.hoje.isoformat(),
            'data_vencimento': self.hoje.isoformat(), 'status': 'pendente',
            'valor': '1000,00', 'chave_pix': 'pessoa@example.com',
        }

    def criar(self, **extras):
        response = self.client.post(reverse('novo_pagamento_colaborador'), {**self.dados, **extras})
        self.assertEqual(response.status_code, 302)
        return PagamentoColaborador.objects.latest('pk')

    def aprovacoes(self, pagamento):
        return AprovacaoRegistro.objects.filter(
            content_type=ContentType.objects.get_for_model(pagamento), object_id=pagamento.pk,
        ).order_by('pk')

    def decidir(self, pagamento, rejeitar=False):
        self.client.force_login(self.luiz)
        response = self.client.post(reverse('rejeitar_registro' if rejeitar else 'aprovar_registro',
            args=[self.aprovacoes(pagamento).last().pk]), {'motivo_rejeicao': 'Revisar valor'} if rejeitar else {})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.operador)

    def comprovante(self):
        return SimpleUploadedFile('comprovante.pdf', b'%PDF-1.4 comprovante folha', content_type='application/pdf')

    def test_novo_pendente_e_encaminhado_para_luiz_sem_baixa(self):
        pagamento = self.criar()
        aprovacao = self.aprovacoes(pagamento).get()
        self.assertEqual(aprovacao.destinatario, self.luiz)
        self.assertEqual(aprovacao.finalidade, 'pagamento')
        self.assertEqual(pagamento.status, 'pendente')
        self.assertContains(self.client.get(reverse('lista_pagamentos_colaboradores')), 'Aguardando aprovação de Luiz')
        response = self.client.post(reverse('marcar_pagamento_como_pago', args=[pagamento.pk]), {
            'comprovante_folha': self.comprovante(),
        })
        self.assertEqual(response.status_code, 200)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertFalse(pagamento.arquivos_importados.exists())

    def test_novo_pago_e_recusado_mesmo_com_comprovante(self):
        response = self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'status': 'pago', 'data_pagamento': self.hoje.isoformat(),
            'comprovante_folha': self.comprovante(),
        })
        self.assertContains(response, 'Cadastre o pagamento como pendente')
        self.assertFalse(PagamentoColaborador.objects.exists())
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_aprovacao_nao_baixa_e_comprovante_continua_obrigatorio(self):
        pagamento = self.criar()
        self.decidir(pagamento)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertIsNone(pagamento.data_pagamento)
        url = reverse('marcar_pagamento_como_pago', args=[pagamento.pk])
        self.assertContains(self.client.post(url), 'Anexe um comprovante')
        self.assertEqual(self.client.post(url, {'comprovante_folha': self.comprovante()}).status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')
        self.assertEqual(pagamento.arquivos_importados.count(), 1)
        self.client.post(url)
        self.assertEqual(pagamento.arquivos_importados.count(), 1)

    def test_edicao_tambem_exige_autorizacao_vigente_para_baixar(self):
        pagamento = self.criar()
        url = reverse('editar_pagamento_colaborador', args=[pagamento.pk])
        dados = {**self.dados, 'status': 'pago', 'data_pagamento': self.hoje.isoformat()}
        self.assertEqual(self.client.post(url, {**dados, 'comprovante_folha': self.comprovante()}).status_code, 200)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.decidir(pagamento)
        self.assertEqual(self.client.post(url, {**dados, 'comprovante_folha': self.comprovante()}).status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')

    def test_alterar_valor_ou_pix_exige_nova_aprovacao_mas_observacao_nao(self):
        pagamento = self.criar()
        self.decidir(pagamento)
        url = reverse('editar_pagamento_colaborador', args=[pagamento.pk])
        self.assertEqual(self.client.post(url, {**self.dados, 'observacao': 'Conferido'}).status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(situacao_aprovacao_pagamento(pagamento), 'aprovado')
        self.assertEqual(self.aprovacoes(pagamento).count(), 1)
        for alteracao in ({'valor': '1200,00'}, {'valor': '1200,00', 'chave_pix': 'outra@example.com'}):
            self.assertEqual(self.client.post(url, {**self.dados, **alteracao}).status_code, 302)
            pagamento.refresh_from_db()
            self.assertEqual(situacao_aprovacao_pagamento(pagamento), 'pendente')
            self.decidir(pagamento)
        self.assertEqual(self.aprovacoes(pagamento).count(), 3)

    def test_nao_pode_trocar_valor_e_baixar_com_autorizacao_anterior(self):
        pagamento = self.criar()
        self.decidir(pagamento)
        response = self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
            **self.dados, 'valor': '9999,00', 'status': 'pago', 'data_pagamento': self.hoje.isoformat(),
            'comprovante_folha': self.comprovante(),
        })
        self.assertEqual(response.status_code, 200)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertEqual(pagamento.valor, Decimal('1000'))

    def test_rejeicao_preserva_obrigacao_e_reenvio_explicito_nao_duplica(self):
        pagamento = self.criar()
        self.decidir(pagamento, rejeitar=True)
        self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), self.dados)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertEqual(self.aprovacoes(pagamento).count(), 1)
        self.assertEqual(situacao_aprovacao_pagamento(pagamento), 'rejeitado')
        url = reverse('solicitar_aprovacao_pagamento_colaborador', args=[pagamento.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.aprovacoes(pagamento).count(), 2)
        self.assertEqual(situacao_aprovacao_pagamento(pagamento), 'pendente')

    def test_retirada_cancela_pedido_de_aprovacao(self):
        pagamento = self.criar()
        self.client.post(reverse('retirar_pagamento_folha', args=[pagamento.pk]))
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'cancelado')
        self.assertEqual(self.aprovacoes(pagamento).get().status, 'cancelado')

    def test_reativar_pagamento_cancelado_requer_nova_autorizacao(self):
        pagamento = self.criar()
        self.decidir(pagamento)
        self.client.post(reverse('retirar_pagamento_folha', args=[pagamento.pk]))
        self.assertEqual(self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), self.dados).status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, 'pendente')
        self.assertEqual(situacao_aprovacao_pagamento(pagamento), 'pendente')
        self.assertEqual(list(self.aprovacoes(pagamento).values_list('status', flat=True)),
                         ['aprovado', 'cancelado', 'pendente'])
        self.assertEqual(self.aprovacoes(pagamento).last().destinatario, self.luiz)

    def test_salario_e_vt_programados_tambem_solicitam_aprovacao(self):
        response = self.client.post(reverse('programacao_salarios'), {
            'mes': self.hoje.strftime('%Y-%m'), 'pessoa_id': self.pessoa.pk,
            'salario_base': '3000', 'dias_trabalhados': '30', 'faltas': '0',
            'gratificacao': '0', 'outros_descontos': '0', 'data_vencimento': self.hoje.isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        segunda = self.hoje - timedelta(days=self.hoje.weekday())
        response = self.client.post(reverse('programacao_vt'), {
            'segunda': segunda.isoformat(), 'pessoa_id': self.pessoa.pk, 'decisao': 'pagar',
            'valor': '100', 'antecipado': 'on', 'dias_jornada': '5', 'dias_previstos': '5',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.count(), 2)
        self.assertEqual(AprovacaoRegistro.objects.filter(destinatario=self.luiz, status='pendente').count(), 2)
        self.client.post(reverse('programacao_vt'), {
            'segunda': segunda.isoformat(), 'pessoa_id': self.pessoa.pk, 'decisao': 'nao',
        })
        vt = PagamentoColaborador.objects.get(tipo='vale_transporte')
        self.assertEqual(self.aprovacoes(vt).get().status, 'cancelado')

    def test_recorrencia_exige_nova_autorizacao_e_desativacao_cancela_fila(self):
        segunda = self.hoje - timedelta(days=self.hoje.weekday())
        pagamento = self.criar(tipo='vale_transporte', competencia=segunda.isoformat(),
            competencia_fim=(segunda + timedelta(days=6)).isoformat(), data_vencimento=segunda.isoformat())
        self.decidir(pagamento)
        self.client.post(reverse('marcar_pagamento_como_pago', args=[pagamento.pk]), {
            'comprovante_folha': self.comprovante(),
        })
        proximo = PagamentoColaborador.objects.exclude(pk=pagamento.pk).get()
        self.assertEqual(proximo.status, 'pendente')
        self.assertEqual(self.aprovacoes(proximo).get().destinatario, self.luiz)
        self.assertEqual(situacao_aprovacao_pagamento(proximo), 'pendente')
        self.pessoa.status = 'inativo'
        self.pessoa.data_desligamento = self.hoje
        self.pessoa.save()
        self.assertEqual(self.aprovacoes(proximo).get().status, 'cancelado')

    @override_settings(APROVADOR_PAGAMENTOS_USERNAME='')
    def test_configuracao_ausente_nao_deixa_pagamento_sem_responsavel(self):
        response = self.client.post(reverse('novo_pagamento_colaborador'), self.dados)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'não está configurado')
        self.assertFalse(PagamentoColaborador.objects.exists())
