"""Diagnostico manual da tela de cadastro de ativos."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
    import django
    django.setup()
    from django.contrib.auth.models import User
    from django.test import Client

    user = User.objects.first()
    if user is None:
        print('Nenhum usuario encontrado.')
        return 2
    client = Client()
    client.force_login(user)
    response = client.get('/manutencao/ativos/novo/')
    print(f'Status code: {response.status_code}')
    return 1 if response.status_code >= 500 else 0


if __name__ == '__main__':
    sys.exit(main())
