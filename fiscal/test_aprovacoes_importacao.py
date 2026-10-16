from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from admissional.models import Colaborador, PagamentoColaborador
from core.models import AprovacaoRegistro, PerfilUsuario
from .services import gerar_pagamentos_fiscais, importar_folha_xlsx
from .tests import build_test_workbook


@override_settings(
    APROVADOR_PAGAMENTOS_USERNAME='luiz_teste',
    APROVADOR_OPERACIONAL_USERNAME='thiago_teste',
)
class AprovacoesImportacaoFiscalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.luiz = User.objects.create_user('luiz_teste')
        cls.thiago = User.objects.create_user('thiago_teste')
        cls.usuario = User.objects.create_user('importador')
        PerfilUsuario.objects.create(usuario=cls.usuario, perfil='financeiro')
        cls.colaborador = Colaborador.objects.create(
            nome='Pessoa Fiscal', cpf='123.456.789-00', tipo_contrato='clt', salario='2000.00',
        )

    def importar(self):
        folha, _ = importar_folha_xlsx(
            content=build_test_workbook(), filename='folha.xlsx',
            competencia=date(2026, 9, 1), usuario=self.usuario,
        )
        return folha

    def test_folha_e_vt_pendentes_sao_encaminhados_a_luiz_sem_duplicidade(self):
        folha = self.importar()
        folha.itens.update(status_fonte='pendente', data_pagamento_fonte=None)
        criados, _ = gerar_pagamentos_fiscais(folha, self.usuario)
        self.assertEqual(criados, 5)
        pagamentos = PagamentoColaborador.objects.filter(status='pendente')
        self.assertEqual(pagamentos.count(), 5)
        self.assertEqual(set(pagamentos.values_list('tipo', flat=True)), {'salario', 'vale_transporte'})
        aprovacoes = AprovacaoRegistro.objects.all()
        self.assertEqual(aprovacoes.count(), 5)
        self.assertEqual(set(aprovacoes.values_list('object_id', flat=True)), set(pagamentos.values_list('pk', flat=True)))
        self.assertFalse(aprovacoes.exclude(
            destinatario=self.luiz, finalidade='pagamento', status='pendente',
            solicitado_por=self.usuario,
            content_type=ContentType.objects.get_for_model(PagamentoColaborador),
        ).exists())
        ids_antes = set(aprovacoes.values_list('pk', flat=True))
        self.assertEqual(gerar_pagamentos_fiscais(folha, self.usuario)[0], 0)
        self.assertEqual(set(aprovacoes.values_list('pk', flat=True)), ids_antes)

    def test_salario_historico_pago_nao_recebe_autorizacao_retroativa(self):
        folha = self.importar()
        gerar_pagamentos_fiscais(folha, self.usuario)
        salario = PagamentoColaborador.objects.get(tipo='salario')
        self.assertEqual(salario.status, 'pago')
        self.assertFalse(AprovacaoRegistro.objects.filter(object_id=salario.pk).exists())
        self.assertEqual(AprovacaoRegistro.objects.filter(destinatario=self.luiz).count(), 4)

    def test_pagamento_pendente_reaproveitado_tambem_exige_aprovacao(self):
        existente = PagamentoColaborador.objects.create(
            colaborador=self.colaborador, tipo='salario', competencia=date(2026, 9, 1),
            competencia_fim=date(2026, 9, 30), valor=Decimal('2100.00'),
            data_vencimento=date(2026, 9, 30), status='pendente',
        )
        folha = self.importar()
        folha.itens.update(status_fonte='pendente', data_pagamento_fonte=None)
        criados, _ = gerar_pagamentos_fiscais(folha, self.usuario)
        self.assertEqual(criados, 4)
        self.assertEqual(folha.itens.get().pagamento_id, existente.pk)
        self.assertEqual(AprovacaoRegistro.objects.get(object_id=existente.pk).destinatario, self.luiz)

    def test_aprovacao_ausente_aborta_lote_sem_pagamentos_ou_vinculos_parciais(self):
        folha = self.importar()
        with override_settings(APROVADOR_PAGAMENTOS_USERNAME='conta_inexistente'):
            with self.assertRaises(ValidationError):
                gerar_pagamentos_fiscais(folha, self.usuario)
        self.assertFalse(PagamentoColaborador.objects.exists())
        self.assertFalse(folha.itens.filter(pagamento__isnull=False).exists())
        self.assertFalse(folha.parcelas_beneficio.filter(pagamento__isnull=False).exists())
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_importacao_somente_historica_dispensa_configuracao_de_aprovador(self):
        folha = self.importar()
        folha.parcelas_beneficio.update(valor=0)
        with override_settings(APROVADOR_PAGAMENTOS_USERNAME=''):
            self.assertEqual(gerar_pagamentos_fiscais(folha, self.usuario)[0], 1)
        self.assertEqual(PagamentoColaborador.objects.get().status, 'pago')
        self.assertFalse(AprovacaoRegistro.objects.exists())

    def test_tela_informa_aprovador_ausente_sem_erro_interno(self):
        folha = self.importar()
        self.client.force_login(self.usuario)
        with override_settings(APROVADOR_PAGAMENTOS_USERNAME=''):
            response = self.client.post(reverse('processar_folha_fiscal', args=[folha.pk]), follow=True)
        self.assertContains(response, 'não está configurado')
        self.assertFalse(PagamentoColaborador.objects.exists())
