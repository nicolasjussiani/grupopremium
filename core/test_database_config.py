from django.test import SimpleTestCase

from core.database_config import database_config


class DatabaseConfigTest(SimpleTestCase):
    def test_serverless_uses_transaction_pooler_without_changing_credentials(self):
        config = database_config(
            'postgresql://postgres.project:p%40ss@aws-1-us-west-2.pooler.supabase.com:5432/postgres',
            serverless=True,
        )
        self.assertEqual(config['PORT'], 6543)
        self.assertEqual(config['PASSWORD'], 'p@ss')
        self.assertEqual(config['USER'], 'postgres.project')
        self.assertEqual(config['NAME'], 'postgres')
        self.assertEqual(config['CONN_MAX_AGE'], 0)
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')
        self.assertEqual(config['OPTIONS']['connect_timeout'], 10)

    def test_local_and_other_postgres_hosts_keep_their_ports(self):
        for host, serverless in (
            ('aws-1-us-west-2.pooler.supabase.com', False),
            ('db.project.supabase.co', True),
            ('postgres.example.com', True),
        ):
            with self.subTest(host=host):
                config = database_config(
                    f'postgresql://user:password@{host}:5432/postgres',
                    serverless=serverless,
                )
                self.assertEqual(config['PORT'], 5432)

    def test_existing_transaction_pooler_is_preserved(self):
        config = database_config(
            'postgresql://user:password@aws-1-us-west-2.pooler.supabase.com:6543/postgres',
            serverless=True,
        )
        self.assertEqual(config['PORT'], 6543)
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])
