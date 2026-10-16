from unittest.mock import patch
from datetime import date

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models import AprovacaoRegistro, PerfilUsuario
from financeiro.models import AuditoriaItem, DocumentoFinanceiro, LancamentoERP
from financeiro.services.ocr_service import extrair_dados_documento


@override_settings(APROVADOR_PAGAMENTOS_USERNAME='luiz_teste', APROVADOR_OPERACIONAL_USERNAME='thiago_teste')
class PagamentoDocumentoTests(TestCase):
    def setUp(self):
        self.ceo = User.objects.create_superuser('thiago_teste')
        self.luiz = User.objects.create_user('luiz_teste')
        self.user = User.objects.create_user('operador-pagamento')
        PerfilUsuario.objects.create(usuario=self.user, perfil='financeiro')
        grupo, _ = Group.objects.get_or_create(name='Financeiro_Operador')
        self.user.groups.add(grupo)
        self.client.force_login(self.user)
        self.dados = dict(tipo='boleto', numero_documento='BOL-1',
                          descricao='Compra de material', valor='150.00',
                          situacao_pagamento='a_pagar', data_vencimento='2026-10-01')

    def criar(self, **campos):
        dados = {**self.dados, **campos}
        return self.client.post(reverse('entrada_documento'), dados)

    def aprovar_pagamento(self, doc):
        aprovacao = AprovacaoRegistro.objects.get(
            content_type=ContentType.objects.get_for_model(doc), object_id=doc.pk, status='pendente',
        )
        cliente = Client()
        cliente.force_login(self.luiz)
        self.assertEqual(cliente.post(reverse('aprovar_registro', args=[aprovacao.pk])).status_code, 302)

    def test_pago_no_cadastro_e_bloqueado_e_baixa_autorizada_sai_de_a_pagar(self):
        response = self.criar(situacao_pagamento='pago', data_pagamento='2026-09-25')
        self.assertContains(response, 'Cadastre como A pagar')
        self.assertFalse(DocumentoFinanceiro.objects.exists())
        self.assertEqual(self.criar().status_code, 302)
        doc = DocumentoFinanceiro.objects.get()
        self.aprovar_pagamento(doc)
        self.assertEqual(self.client.post(reverse('atualizar_pagamento_documento', args=[doc.pk]), {
            'situacao_pagamento': 'pago', 'data_pagamento': '2026-09-25',
        }).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.data_pagamento, date(2026, 9, 25))
        self.assertEqual(doc.situacao_pagamento, 'pago')
        self.assertEqual(doc.status, 'em_auditoria')
        painel = self.client.get(reverse('painel_financeiro'), {'pagamento': 'a_pagar'})
        self.assertEqual(list(painel.context['pagamentos']), [])
        painel = self.client.get(reverse('painel_financeiro'), {'pagamento': 'pago'})
        self.assertContains(painel, 'Compra de material')

    def test_rejeita_pago_sem_data_e_status_invalido(self):
        for campos in ({'situacao_pagamento': 'pago'},
                       {'situacao_pagamento': 'invalido'},
                       {'situacao_pagamento': 'pago', 'data_pagamento': '2026-02-30'}):
            with self.subTest(campos=campos):
                self.assertEqual(self.criar(**campos).status_code, 200)
                self.assertFalse(DocumentoFinanceiro.objects.exists())

    def test_baixa_preserva_vencimento_e_auditoria_e_reabertura_e_bloqueada(self):
        self.criar()
        doc = DocumentoFinanceiro.objects.get()
        url = reverse('atualizar_pagamento_documento', args=[doc.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'situacao_pagamento': 'pago'}).status_code, 400)
        self.aprovar_pagamento(doc)
        self.assertEqual(self.client.post(url, {'situacao_pagamento': 'pago', 'data_pagamento': '2026-09-25'}).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'pago')
        self.assertEqual(doc.data_vencimento, date(2026, 10, 1))
        self.assertEqual(doc.status, 'em_auditoria')
        self.assertEqual(self.client.post(url, {'situacao_pagamento': 'a_pagar', 'data_pagamento': '2026-09-25'}).status_code, 400)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'pago')
        self.assertEqual(doc.data_pagamento, date(2026, 9, 25))

    def test_usuario_sem_permissao_nao_altera_pagamento(self):
        self.criar()
        doc = DocumentoFinanceiro.objects.get()
        leitor = User.objects.create_user('sem-permissao')
        leitor.user_permissions.add(Permission.objects.get(codename='view_documentofinanceiro'))
        self.client.force_login(leitor)
        response = self.client.post(reverse('atualizar_pagamento_documento', args=[doc.pk]),
                                    {'situacao_pagamento': 'pago', 'data_pagamento': '2026-09-25'})
        self.assertEqual(response.status_code, 403)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'a_pagar')
        self.assertNotContains(self.client.get(reverse('detalhe_documento', args=[doc.pk])), 'Salvar pagamento')

    def test_documento_sem_classificacao_nao_e_assumido_como_divida(self):
        doc = DocumentoFinanceiro.objects.create(tipo='boleto', numero_documento='ANTIGO', descricao='Antigo', valor=20)
        self.assertEqual(doc.situacao_pagamento, 'nao_informado')
        self.assertContains(self.client.get(reverse('painel_financeiro'), {'pagamento': 'nao_informado'}), 'ANTIGO')

    def test_lancamento_erp_salva_pagamento_no_documento(self):
        self.criar()
        doc = DocumentoFinanceiro.objects.get()
        doc.status = 'aprovado_lancamento'
        doc.save()
        doc.auditoria.update(status='ok')
        dados = dict(descricao='Material', tipo='debito', competencia='2026-09-01', centro_custo='ADM', situacao_pagamento='pago')
        url = reverse('lancar_erp', args=[doc.pk])
        self.assertEqual(self.client.post(url, dados).status_code, 200)
        self.assertFalse(LancamentoERP.objects.exists())
        self.aprovar_pagamento(doc)
        dados['data_pagamento'] = '2026-09-25'
        self.assertEqual(self.client.post(url, dados).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'pago')
        self.assertEqual(doc.status, 'lancado')

    def test_erro_de_pagamento_preserva_dados_digitados_no_lancamento(self):
        self.criar()
        doc = DocumentoFinanceiro.objects.get()
        doc.status = 'aprovado_lancamento'
        doc.save()
        doc.auditoria.update(status='ok')
        response = self.client.post(reverse('lancar_erp', args=[doc.pk]), {
            'descricao': 'Descricao manual especifica', 'tipo': 'provisao',
            'competencia': '2026-09-01', 'centro_custo': 'CENTRO MANUAL',
            'situacao_pagamento': 'pago',
        })
        self.assertContains(response, 'value="Descricao manual especifica"')
        self.assertContains(response, 'value="2026-09-01"')
        self.assertContains(response, 'value="CENTRO MANUAL"')
        self.assertContains(response, 'value="provisao" selected')
        self.assertFalse(LancamentoERP.objects.exists())

    def test_aprovar_documento_nao_quita_e_baixa_funciona_apos_arquivamento(self):
        self.client.force_login(self.ceo)
        self.criar()
        doc = DocumentoFinanceiro.objects.get()
        self.client.post(reverse('auditoria_documento', args=[doc.pk]), {
            f'item_{item.pk}': 'ok' for item in doc.auditoria.all()
        })
        self.client.post(reverse('lancar_erp', args=[doc.pk]), {
            'descricao': 'Boleto pendente', 'tipo': 'debito',
            'competencia': '2026-09-01', 'centro_custo': 'ADM',
            'situacao_pagamento': 'a_pagar',
        })
        lancamento = LancamentoERP.objects.get(documento=doc)
        self.client.post(reverse('validar_lancamento', args=[lancamento.pk]), {'acao': 'validar'})
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'arquivado')
        self.assertEqual(doc.situacao_pagamento, 'a_pagar')
        self.assertContains(self.client.get(reverse('painel_financeiro'), {'pagamento': 'a_pagar'}), 'Compra de material')
        self.aprovar_pagamento(doc)
        self.client.post(reverse('atualizar_pagamento_documento', args=[doc.pk]), {
            'situacao_pagamento': 'pago', 'data_pagamento': '2026-09-25',
        })
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'arquivado')
        self.assertEqual(doc.situacao_pagamento, 'pago')
        self.assertEqual(list(self.client.get(reverse('painel_financeiro'), {'pagamento': 'a_pagar'}).context['pagamentos']), [])

    def test_pagamento_protegido_por_csrf(self):
        from django.test import Client
        self.criar()
        doc = DocumentoFinanceiro.objects.get()
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.user)
        url = reverse('atualizar_pagamento_documento', args=[doc.pk])
        self.assertEqual(cliente.post(url, {'situacao_pagamento': 'pago', 'data_pagamento': '2026-09-25'}).status_code, 403)
        doc.refresh_from_db()
        self.assertEqual(doc.situacao_pagamento, 'a_pagar')


class LeituraProvisoriaDocumentoTests(SimpleTestCase):
    @patch.dict('os.environ', {}, clear=True)
    def test_sem_chave_api_usa_modo_local(self):
        dados = extrair_dados_documento(b'\x89PNG\r\n\x1a\n', 'image/png')
        self.assertEqual(dados['_modo'], 'local')
        self.assertIn('chave da IA', dados['_aviso'])
        self.assertEqual(dados['produtos'], [])


@override_settings(APROVADOR_PAGAMENTOS_USERNAME='luiz_teste', APROVADOR_OPERACIONAL_USERNAME='thiago_teste')
class EntradaDocumentoOpcionalTests(TestCase):
    def setUp(self):
        User.objects.create_user('thiago_teste')
        User.objects.create_user('luiz_teste')
        self.user = User.objects.create_user('financeiro-opcional', password='senha-forte-123')
        PerfilUsuario.objects.create(usuario=self.user, perfil='financeiro')
        grupo, _ = Group.objects.get_or_create(name='Financeiro_Operador')
        self.user.groups.add(grupo)
        self.client.force_login(self.user)

    @staticmethod
    def _pdf():
        return SimpleUploadedFile(
            'documento.pdf', b'%PDF-1.4\nconteudo de teste', content_type='application/pdf'
        )

    def test_novo_documento_aceita_campos_complementares_vazios(self):
        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'nota_fiscal',
            'numero_documento': 'NF-OPCIONAL-001',
            'descricao': 'Documento aguardando complementacao',
            'valor': '125.50',
            'arquivo_pdf': self._pdf(),
        })

        self.assertEqual(response.status_code, 302)
        documento = DocumentoFinanceiro.objects.get(numero_documento='NF-OPCIONAL-001')
        self.assertEqual(documento.cnpj_emitente, '')
        self.assertEqual(documento.razao_social_emitente, '')
        self.assertEqual(documento.centro_custo, '')
        self.assertEqual(documento.unidade, '')
        self.assertIsNone(documento.data_emissao)
        self.assertIsNone(documento.data_vencimento)
        self.assertEqual(documento.auditoria.count(), len(AuditoriaItem.ITENS_CHECKLIST))

    def test_novo_documento_aceita_cadastro_sem_pdf(self):
        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'nota_fiscal',
            'numero_documento': 'NF-SEM-PDF-001',
            'descricao': 'Documento cadastrado sem anexo',
            'valor': '89.90',
        })

        self.assertEqual(response.status_code, 302)
        documento = DocumentoFinanceiro.objects.get(numero_documento='NF-SEM-PDF-001')
        self.assertFalse(documento.arquivo)

    def test_novo_documento_aceita_imagem_no_campo_pdf(self):
        imagem = SimpleUploadedFile(
            'documento.png', b'\x89PNG\r\n\x1a\nconteudo', content_type='image/png'
        )

        response = self.client.post(reverse('entrada_documento'), {
            'tipo': 'nota_fiscal',
            'numero_documento': 'NF-IMAGEM-001',
            'descricao': 'Comprovante em imagem',
            'valor': '89.90',
            'arquivo_pdf': imagem,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DocumentoFinanceiro.objects.filter(numero_documento='NF-IMAGEM-001').exists()
        )

    def test_formulario_indica_campos_complementares_como_opcionais(self):
        response = self.client.get(reverse('entrada_documento'))

        self.assertContains(response, 'Obrigatórios somente')
        self.assertNotContains(
            response, 'name="cnpj_emitente" class="form-control" required'
        )
        self.assertNotContains(
            response, 'name="data_vencimento" class="form-control" required'
        )
        self.assertContains(response, 'inclusive o arquivo')
        self.assertContains(response, 'Documento financeiro em PDF')
        self.assertContains(response, 'com até 50 MB')
        self.assertNotContains(
            response, 'name="arquivo_pdf" accept=".pdf,application/pdf" class="form-control" required'
        )

    def test_campo_pdf_aparece_antes_dos_dados_do_documento(self):
        response = self.client.get(reverse('entrada_documento'))
        conteudo = response.content.decode()

        self.assertLess(
            conteudo.index('name="arquivo_pdf"'),
            conteudo.index('name="tipo"'),
        )

    def test_centro_de_custo_pode_ser_informado_no_lancamento(self):
        documento = DocumentoFinanceiro.objects.create(
            tipo='nota_fiscal', numero_documento='NF-OPCIONAL-002',
            descricao='Documento sem classificacao inicial', valor='50.00',
            status='aprovado_lancamento',
        )
        for item, _ in AuditoriaItem.ITENS_CHECKLIST:
            AuditoriaItem.objects.create(documento=documento, item=item, status='ok')

        response = self.client.post(reverse('lancar_erp', args=[documento.pk]), {
            'descricao': 'Lancamento classificado depois',
            'tipo': 'debito',
            'competencia': '2026-09-01',
            'centro_custo': 'ADM',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LancamentoERP.objects.get(documento=documento).centro_custo, 'ADM')
