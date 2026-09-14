from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Colaborador, DocumentoColaborador


class ListaColaboradoresContratoTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='consulta_colaboradores',
            email='consulta@example.com',
            password='senha-teste',
        )
        self.client.force_login(self.user)

    def test_exibe_contrato_no_lugar_da_marca(self):
        Colaborador.objects.create(
            nome='Colaborador Teste',
            cpf='12345678901',
            cargo='Lavador',
            unidade='Bauru',
            contrato='MOVIDA SN',
            marca='eco_premium',
            data_admissao=date(2026, 3, 6),
            status='ativo',
        )

        response = self.client.get(reverse('lista_colaboradores'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<th>Contrato</th>', html=True)
        self.assertContains(response, 'MOVIDA SN')
        self.assertNotContains(response, '<th>Marca</th>', html=True)
        self.assertNotContains(response, 'Eco Premium')

    def test_indica_quando_contrato_nao_foi_informado(self):
        Colaborador.objects.create(
            nome='Colaborador Sem Contrato',
            cpf='10987654321',
            cargo='Auxiliar',
            unidade='Campinas',
            contrato='',
            data_admissao=date(2026, 4, 10),
            status='ativo',
        )

        response = self.client.get(reverse('lista_colaboradores'))

        self.assertContains(response, 'Não informado')

    def test_desativar_preserva_colaborador_e_documentos(self):
        colaborador = Colaborador.objects.create(
            nome='Pessoa a Desativar', cpf='98765432100', cargo='Auxiliar',
            unidade='Matriz', data_admissao=date(2026, 4, 10), status='ativo',
        )
        documento = DocumentoColaborador.objects.create(
            colaborador=colaborador, tipo='contrato',
            arquivo='admissional/colaboradores/teste/contrato.pdf',
        )

        response = self.client.post(reverse('excluir_colaborador', args=[colaborador.pk]))

        self.assertRedirects(response, f"{reverse('lista_colaboradores')}?status=inativo")
        colaborador.refresh_from_db()
        self.assertEqual(colaborador.status, 'inativo')
        self.assertTrue(Colaborador.objects.filter(pk=colaborador.pk).exists())
        self.assertTrue(DocumentoColaborador.objects.filter(pk=documento.pk).exists())

    def test_lista_permite_consultar_inativos_e_reativar(self):
        inativo = Colaborador.objects.create(
            nome='Pessoa Inativa', cpf='98765432101', cargo='Auxiliar',
            unidade='Matriz', data_admissao=date(2026, 4, 10), status='inativo',
        )

        lista = self.client.get(reverse('lista_colaboradores'), {'status': 'inativo'})

        self.assertContains(lista, inativo.nome)
        self.assertContains(lista, reverse('reativar_colaborador', args=[inativo.pk]))
        response = self.client.post(reverse('reativar_colaborador', args=[inativo.pk]))
        self.assertRedirects(response, reverse('lista_colaboradores'))
        inativo.refresh_from_db()
        self.assertEqual(inativo.status, 'ativo')

    def test_confirmacao_explica_que_dados_nao_serao_excluidos(self):
        colaborador = Colaborador.objects.create(
            nome='Pessoa Preservada', cpf='98765432102', cargo='Auxiliar',
            unidade='Matriz', data_admissao=date(2026, 4, 10),
        )

        response = self.client.get(reverse('excluir_colaborador', args=[colaborador.pk]))

        self.assertContains(response, 'Desativar Colaborador')
        self.assertContains(response, 'documentos, EPIs e demais registros serão preservados')
        self.assertNotContains(response, 'removerá todos os registros')

    def test_delete_direto_no_modelo_tambem_apenas_desativa(self):
        colaborador = Colaborador.objects.create(
            nome='Pessoa Protegida', cpf='98765432103', cargo='Auxiliar',
            unidade='Matriz', data_admissao=date(2026, 4, 10),
        )

        colaborador.delete()

        colaborador.refresh_from_db()
        self.assertEqual(colaborador.status, 'inativo')

    def test_delete_em_lote_tambem_apenas_desativa(self):
        colaborador = Colaborador.objects.create(
            nome='Pessoa Protegida em Lote', cpf='98765432104', cargo='Auxiliar',
            unidade='Matriz', data_admissao=date(2026, 4, 10),
        )

        Colaborador.objects.filter(pk=colaborador.pk).delete()

        colaborador.refresh_from_db()
        self.assertEqual(colaborador.status, 'inativo')
