"""Helpers para normalizar endpoints do Supabase Storage."""


def normalize_supabase_s3_endpoint(value):
    """Retorna o endpoint S3 direto sem duplicar o subdominio ``storage``."""
    if not value:
        return value

    endpoint = value.strip().rstrip('/')
    # Corrige configuracoes que ja tenham sido salvas com a duplicacao gerada
    # pela normalizacao antiga.
    while '.storage.storage.supabase.co' in endpoint:
        endpoint = endpoint.replace(
            '.storage.storage.supabase.co',
            '.storage.supabase.co',
        )

    legacy_suffix = '.supabase.co/storage/v1/s3'
    direct_suffix = '.storage.supabase.co/storage/v1/s3'
    if endpoint.endswith(legacy_suffix) and not endpoint.endswith(direct_suffix):
        endpoint = f'{endpoint[:-len(legacy_suffix)]}{direct_suffix}'
    return endpoint
