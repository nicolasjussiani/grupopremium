from django.test import SimpleTestCase

from core.storage_endpoints import normalize_supabase_s3_endpoint


class SupabaseStorageEndpointTests(SimpleTestCase):
    def test_converte_endpoint_legado_para_endpoint_direto(self):
        self.assertEqual(
            normalize_supabase_s3_endpoint(
                'https://projeto.supabase.co/storage/v1/s3'
            ),
            'https://projeto.storage.supabase.co/storage/v1/s3',
        )

    def test_mantem_endpoint_direto_sem_duplicar_storage(self):
        self.assertEqual(
            normalize_supabase_s3_endpoint(
                'https://projeto.storage.supabase.co/storage/v1/s3'
            ),
            'https://projeto.storage.supabase.co/storage/v1/s3',
        )

    def test_corrige_endpoint_ja_duplicado(self):
        self.assertEqual(
            normalize_supabase_s3_endpoint(
                'https://projeto.storage.storage.supabase.co/storage/v1/s3/'
            ),
            'https://projeto.storage.supabase.co/storage/v1/s3',
        )

    def test_aceita_valor_ausente(self):
        self.assertIsNone(normalize_supabase_s3_endpoint(None))
