from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Admissao, Colaborador, DocumentoAdmissional, PagamentoColaborador


class AprovacaoDocumentosAdmissaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser('rh-documentos')

    def setUp(self):
        self.client.force_login(self.usuario)
        self.admissao = Admissao.objects.create(
            candidato_nome='Pessoa candidata', candidato_email='pessoa@example.com',
            vaga_nome='Operador', unidade_destino='Matriz', status='documentos_em_analise',
        )
        self.url = reverse('avancar_admissao', args=[self.admissao.pk])

    def test_documentos_ausentes_ou_nao_aprovados_bloqueiam_cadastro(self):
        for status in (None, 'pendente', 'rejeitado', 'aguardando_analise'):
            with self.subTest(status=status):
                self.admissao.documentos.all().delete()
                if status:
                    DocumentoAdmissional.objects.create(admissao=self.admissao, tipo='cpf', status=status)
                response = self.client.post(self.url, {'novo_status': 'cadastro_sistema'})
                self.assertEqual(response.status_code, 302)
                self.admissao.refresh_from_db()
                self.assertEqual(self.admissao.status, 'documentos_em_analise')

    def test_documentos_aprovados_liberam_cadastro(self):
        DocumentoAdmissional.objects.create(admissao=self.admissao, tipo='cpf', status='aprovado')
        self.client.post(self.url, {'novo_status': 'cadastro_sistema'})
        self.admissao.refresh_from_db()
        self.assertEqual(self.admissao.status, 'cadastro_sistema')

    def test_processo_legado_nao_conclui_nem_cria_colaborador_com_documento_pendente(self):
        self.admissao.status = 'liberado'
        self.admissao.save()
        DocumentoAdmissional.objects.create(admissao=self.admissao, tipo='cpf', status='pendente')
        self.client.post(self.url, {
            'novo_status': 'concluido', 'gerar_colaborador': 'sim',
            'cpf': '123.456.789-01', 'data_inicio': '2026-10-01',
        })
        self.admissao.refresh_from_db()
        self.assertEqual(self.admissao.status, 'liberado')
        self.assertIsNone(self.admissao.concluido_em)
        self.assertFalse(Colaborador.objects.exists())

    def test_etapas_de_analise_continuam_disponiveis_com_pendencias(self):
        self.admissao.status = 'aguardando_documentos'
        self.admissao.save()
        for destino in ('documentos_em_analise', 'documentos_pendentes', 'documentos_em_analise'):
            self.client.post(self.url, {'novo_status': destino})
            self.admissao.refresh_from_db()
            self.assertEqual(self.admissao.status, destino)

    def test_reaprovar_documento_nao_regride_etapas_avancadas(self):
        documento = DocumentoAdmissional.objects.create(admissao=self.admissao, tipo='cpf', status='aprovado')
        url = reverse('atualizar_documento', args=[self.admissao.pk, documento.pk])
        for status in ('cadastro_sistema', 'contrato_gerado', 'integracao', 'epis_entregues', 'liberado'):
            with self.subTest(status=status):
                self.admissao.status = status
                self.admissao.save()
                self.assertEqual(self.client.post(url, {'status': 'aprovado'}).status_code, 302)
                self.admissao.refresh_from_db()
                self.assertEqual(self.admissao.status, status)

    def test_documentacao_concluida_preserva_status_arquivo_e_data_de_conclusao(self):
        self.admissao.status = 'concluido'
        self.admissao.concluido_em = timezone.now()
        self.admissao.save()
        concluido_em = self.admissao.concluido_em
        documento = DocumentoAdmissional.objects.create(
            admissao=self.admissao, tipo='cpf', status='aprovado',
            observacao='Conferido', arquivo_nuvem='documentos_admissional/original.pdf',
        )
        url = reverse('atualizar_documento', args=[self.admissao.pk, documento.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        for status in ('aprovado', 'rejeitado', 'pendente'):
            with self.subTest(status=status):
                response = self.client.post(url, {
                    'status': status, 'observacao': 'Alterar concluído',
                    'arquivo': SimpleUploadedFile('outro.pdf', b'%PDF-1.4 teste', content_type='application/pdf'),
                })
                self.assertEqual(response.status_code, 302)
                self.admissao.refresh_from_db()
                documento.refresh_from_db()
                self.assertEqual(self.admissao.status, 'concluido')
                self.assertEqual(self.admissao.concluido_em, concluido_em)
                self.assertEqual(documento.status, 'aprovado')
                self.assertEqual(documento.observacao, 'Conferido')
                self.assertEqual(documento.arquivo_nuvem.name, 'documentos_admissional/original.pdf')
        detalhe = self.client.get(reverse('detalhe_admissao', args=[self.admissao.pk]))
        self.assertNotContains(detalhe, 'Atualizar Status / Anexar')
        self.assertContains(detalhe, reverse('baixar_documento', args=[self.admissao.pk, documento.pk]))


class DistratoColaboradorDesligadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser('rh-distrato')

    def setUp(self):
        self.client.force_login(self.usuario)
        self.hoje = timezone.localdate()
        self.pessoa = Colaborador.objects.create(
            nome='Pessoa desligada', status='desligado', data_desligamento=self.hoje,
        )
        self.dados = {
            'colaborador': self.pessoa.pk, 'tipo': 'distrato', 'competencia': self.hoje.isoformat(),
            'competencia_fim': self.hoje.isoformat(), 'data_vencimento': self.hoje.isoformat(),
            'valor': '1000,00', 'status': 'pendente',
        }

    def test_distrato_de_desligado_pode_ser_criado_editado_listado_e_pago(self):
        formulario = self.client.get(reverse('novo_pagamento_colaborador'))
        self.assertContains(formulario, self.pessoa.nome)
        self.assertEqual(self.client.post(reverse('novo_pagamento_colaborador'), self.dados).status_code, 302)
        pagamento = PagamentoColaborador.objects.get()
        self.assertEqual(self.client.post(reverse('editar_pagamento_colaborador', args=[pagamento.pk]), {
            **self.dados, 'valor': '1200,00',
        }).status_code, 302)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.valor, Decimal('1200'))
        for tela in ('lista_pagamentos_colaboradores', 'relatorio_folha_pagamento'):
            resposta = self.client.get(reverse(tela))
            self.assertContains(resposta, self.pessoa.nome)
            self.assertEqual(resposta.context['total_pendente'], Decimal('1200'))
        painel = self.client.get(reverse('painel_financeiro'))
        self.assertEqual(painel.context['folha_mes_pendente'], Decimal('1200'))
        comprovante = SimpleUploadedFile('distrato.pdf', b'%PDF-1.4 comprovante distrato', content_type='application/pdf')
        self.assertEqual(self.client.post(reverse('marcar_pagamento_como_pago', args=[pagamento.pk]), {
            'comprovante_folha': comprovante,
        }).status_code, 302)
        pagamento.refresh_from_db()
        self.pessoa.refresh_from_db()
        self.assertEqual(pagamento.status, 'pago')
        self.assertEqual(pagamento.arquivos_importados.count(), 1)
        self.assertEqual(self.pessoa.status, 'desligado')
        self.assertContains(self.client.get(reverse('lista_pagamentos_colaboradores')), self.pessoa.nome)

    def test_inativo_tambem_pode_receber_distrato(self):
        self.pessoa.status = 'inativo'
        self.pessoa.save()
        self.assertEqual(self.client.post(reverse('novo_pagamento_colaborador'), self.dados).status_code, 302)
        self.assertEqual(PagamentoColaborador.objects.get().tipo, 'distrato')

    def test_pagamentos_regulares_continuam_bloqueados_para_desligados(self):
        for tipo in ('salario', 'vale_transporte', 'prestacao_servico'):
            with self.subTest(tipo=tipo):
                resposta = self.client.post(reverse('novo_pagamento_colaborador'), {**self.dados, 'tipo': tipo})
                self.assertEqual(resposta.status_code, 200)
                self.assertIn('colaborador', resposta.context['form'].errors)
                self.assertFalse(PagamentoColaborador.objects.exists())

    def test_desativacao_preserva_distrato_futuro_na_folha(self):
        self.pessoa.status = 'ativo'
        self.pessoa.save()
        vencimento = self.hoje + timedelta(days=5)
        self.client.post(reverse('novo_pagamento_colaborador'), {
            **self.dados, 'data_vencimento': vencimento.isoformat(),
        })
        self.pessoa.status = 'inativo'
        self.pessoa.save()
        pagamento = PagamentoColaborador.objects.get()
        self.assertEqual(pagamento.status, 'pendente')
        resposta = self.client.get(reverse('lista_pagamentos_colaboradores'), {
            'data_inicio': self.hoje.isoformat(), 'data_fim': vencimento.isoformat(),
        })
        self.assertContains(resposta, self.pessoa.nome)
