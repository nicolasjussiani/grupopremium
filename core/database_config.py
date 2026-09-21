"""Connection settings for the Supabase pooler and serverless workers."""

import dj_database_url


def database_config(url, *, serverless=False):
    config = dj_database_url.parse(url, conn_max_age=0, ssl_require=True)
    host = config.get('HOST', '').lower()
    if (
        serverless
        and config['ENGINE'] == 'django.db.backends.postgresql'
        and host.endswith('.pooler.supabase.com')
    ):
        # Session mode dedicates a backend to each worker, exhausting small pools.
        if str(config.get('PORT') or '5432') == '5432':
            config['PORT'] = 6543
        config['DISABLE_SERVER_SIDE_CURSORS'] = True
        config['CONN_MAX_AGE'] = 0
        config.setdefault('OPTIONS', {}).setdefault('connect_timeout', 10)
    return config
