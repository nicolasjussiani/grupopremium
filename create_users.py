"""Cria usuarios operacionais usando senhas fornecidas pelo ambiente."""

import os
import sys

import django


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from core.models import PerfilUsuario


USUARIOS = [
    ('ceo_premium', 'ERP_CEO_PASSWORD', True, 'admin', 'Admin_Global'),
    ('rh_premium', 'ERP_RH_PASSWORD', False, 'rh', 'Admissional_RH'),
    ('compras_premium', 'ERP_COMPRAS_PASSWORD', False, 'compras', 'Compras_Aprovador'),
    ('financeiro_premium', 'ERP_FINANCEIRO_PASSWORD', False, 'financeiro', 'Financeiro_Aprovador'),
    ('sesmet_premium', 'ERP_SESMET_PASSWORD', False, 'sesmet', 'SESMET_Gestor'),
]


def main():
    faltantes = [password_env for _, password_env, *_ in USUARIOS if not os.environ.get(password_env)]
    if faltantes:
        print('Variaveis de senha ausentes: ' + ', '.join(faltantes), file=sys.stderr)
        raise SystemExit(1)

    for username, password_env, *_ in USUARIOS:
        try:
            validate_password(os.environ[password_env], User(username=username))
        except ValidationError as exc:
            print(f'Senha invalida para {username}: {"; ".join(exc.messages)}', file=sys.stderr)
            raise SystemExit(1)

    for username, password_env, is_superuser, perfil, grupo_nome in USUARIOS:
        user, created = User.objects.get_or_create(username=username)
        user.set_password(os.environ[password_env])
        user.is_active = True
        user.is_staff = is_superuser
        user.is_superuser = is_superuser
        user.save()
        PerfilUsuario.objects.update_or_create(usuario=user, defaults={'perfil': perfil})
        grupo = Group.objects.filter(name=grupo_nome).first()
        if grupo:
            user.groups.add(grupo)
        verbo = 'Criado' if created else 'Atualizado'
        print(f'{verbo}: {username} ({perfil})')


if __name__ == '__main__':
    main()
