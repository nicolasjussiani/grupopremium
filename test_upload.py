"""Diagnostico manual do backend de armazenamento configurado."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    backend = settings.STORAGES['default']['BACKEND']
    print(f'Storage backend: {backend}')
    path = None
    try:
        path = default_storage.save(
            'diagnosticos/teste_upload.txt',
            ContentFile(b'Arquivo de teste do storage'),
        )
        print(f'Upload concluido: {path}')
        print(f'URL: {default_storage.url(path)}')
    except Exception as exc:
        print(f'Falha no upload: {exc}')
        return 1
    finally:
        if path:
            default_storage.delete(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
