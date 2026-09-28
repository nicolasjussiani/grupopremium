from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client, TestCase
from django.urls import reverse

from core import test_full_site
from core.models import ArquivoImportado, LogAtividade, PerfilUsuario
from core.storage_organization import FILE_FIELDS


class ExcluirAnexoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_full_site.FullSiteRouteTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.user)

    def url(self, obj, field='arquivo'):
        return reverse('excluir_anexo', args=[obj._meta.label_lower, obj.pk, field])

    def remove(self, obj, field='arquivo', **extra):
        url = self.url(obj, field)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, {'confirmacao': page.context['confirmacao'], **extra})

    def attach(self, obj, field, name=None):
        name = default_storage.save(name or f'test-anexos/{obj._meta.label}/{field}.pdf', ContentFile(b'attachment'))
        type(obj).objects.filter(pk=obj.pk).update(**{field: name})
        obj.refresh_from_db()
        return name

    def test_all_registered_file_fields_can_be_removed_without_deleting_business_records(self):
        objects = [self.colaborador, self.documento_admissional, self.candidato,
                   self.talento, self.documento_financeiro, self.material,
                   self.requisicao_compra, self.equipamento, self.ativo, self.manutencao]
        for obj in objects:
            for field in FILE_FIELDS[obj._meta.label]:
                with self.subTest(model=obj._meta.label, field=field):
                    name = self.attach(obj, field)
                    self.assertEqual(self.remove(obj, field).status_code, 302)
                    obj.refresh_from_db()
                    self.assertFalse(getattr(obj, field))
                    self.assertFalse(default_storage.exists(name))
        self.documento_financeiro.refresh_from_db()
        self.assertEqual(self.documento_financeiro.status, 'aprovado_lancamento')
        self.assertEqual(self.documento_financeiro.valor, 100)
        self.assertTrue(type(self.lancamento).objects.filter(pk=self.lancamento.pk).exists())

    def test_legacy_binary_attachments_are_cleared(self):
        for obj, field, legacy in [(self.candidato, 'arquivo', 'arquivo_pdf'),
                                   (self.talento, 'arquivo', 'arquivo_pdf'),
                                   (self.documento_financeiro, 'arquivo', 'arquivo_pdf'),
                                   (self.documento_admissional, 'arquivo_nuvem', 'arquivo')]:
            self.assertEqual(self.remove(obj, field).status_code, 302)
            obj.refresh_from_db()
            self.assertFalse(getattr(obj, legacy))
            self.assertEqual(self.client.get(self.url(obj, field)).status_code, 404)
        self.assertEqual(self.documento_admissional.status, 'pendente')

    def test_shared_storage_file_is_preserved_until_last_reference_is_removed(self):
        name = self.attach(self.colaborador, 'anexo_cpf')
        type(self.material).objects.filter(pk=self.material.pk).update(foto=name)
        self.remove(self.colaborador, 'anexo_cpf')
        self.assertTrue(default_storage.exists(name))
        self.remove(self.material, 'foto')
        self.assertFalse(default_storage.exists(name))

    def test_colaborador_document_row_is_removed_but_colaborador_is_preserved(self):
        name = self.attach(self.documento_colaborador, 'arquivo')
        self.remove(self.documento_colaborador)
        self.assertFalse(type(self.documento_colaborador).objects.filter(pk=self.documento_colaborador.pk).exists())
        self.colaborador.refresh_from_db()
        self.assertFalse(default_storage.exists(name))

    def test_payment_proof_removal_preserves_paid_status_and_amount(self):
        payment = self.pagamento_colaborador
        type(payment).objects.filter(pk=payment.pk).update(status='pago')
        proof = ArquivoImportado.objects.create(
            arquivo='test-anexos/proof.pdf', nome_original='proof.pdf', sha256='c'*64,
            content_type=ContentType.objects.get_for_model(payment), object_id=payment.pk,
            area='financeiro', importado_por=self.user)
        self.remove(proof)
        self.assertFalse(ArquivoImportado.objects.filter(pk=proof.pk).exists())
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pago')
        self.assertEqual(payment.valor, 2500)

    def test_fiscal_source_removal_preserves_imported_sheet(self):
        name = self.attach(self.arquivo_importado, 'arquivo')
        self.remove(self.arquivo_importado)
        self.folha_fiscal.refresh_from_db()
        self.arquivo_importado.refresh_from_db()
        self.assertFalse(self.arquivo_importado.arquivo)
        self.assertFalse(default_storage.exists(name))
        self.assertEqual(self.folha_fiscal.arquivo_origem_id, self.arquivo_importado.pk)
        self.assertEqual(self.client.get(reverse('baixar_arquivo_importado', args=[self.arquivo_importado.pk])).status_code, 404)

    def test_get_invalid_token_and_stale_confirmation_do_not_delete(self):
        url = self.url(self.colaborador, 'anexo_cpf')
        page = self.client.get(url)
        self.colaborador.refresh_from_db()
        self.assertTrue(self.colaborador.anexo_cpf)
        self.assertEqual(self.client.post(url).status_code, 409)
        self.assertEqual(self.client.post(url, {'confirmacao': 'tampered'}).status_code, 409)
        new_name = self.attach(self.colaborador, 'anexo_cpf', 'test-anexos/replacement.pdf')
        self.assertEqual(self.client.post(url, {'confirmacao': page.context['confirmacao']}).status_code, 409)
        self.colaborador.refresh_from_db()
        self.assertEqual(self.colaborador.anexo_cpf.name, new_name)
        self.assertTrue(default_storage.exists(new_name))

    def test_permissions_and_field_allowlist(self):
        url = self.url(self.colaborador, 'anexo_cpf')
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        user = User.objects.create_user('rh-anexos')
        PerfilUsuario.objects.create(usuario=user, perfil='rh')
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(self.url(self.documento_financeiro)).status_code, 403)
        self.assertEqual(self.client.post(self.url(self.documento_financeiro)).status_code, 403)
        self.assertEqual(self.client.get(self.url(self.colaborador, 'nome')).status_code, 404)
        self.assertEqual(self.client.get(reverse('excluir_anexo', args=['auth.user', user.pk, 'password'])).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 405)
        PerfilUsuario.objects.filter(usuario=user).update(perfil='colaborador')
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_csrf_and_safe_redirect(self):
        url = self.url(self.colaborador, 'anexo_cpf')
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(url).status_code, 403)
        response = self.remove(self.colaborador, 'anexo_cpf', next='//evil.example/')
        self.assertEqual(response.url, reverse('dashboard'))

    def test_rollback_preserves_attachment_when_database_write_fails(self):
        name = self.attach(self.colaborador, 'anexo_cpf')
        url = self.url(self.colaborador, 'anexo_cpf')
        token = self.client.get(url).context['confirmacao']
        with patch.object(LogAtividade.objects, 'create', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.post(url, {'confirmacao': token})
        self.colaborador.refresh_from_db()
        self.assertEqual(self.colaborador.anexo_cpf.name, name)
        self.assertTrue(default_storage.exists(name))
