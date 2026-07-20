import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from django.contrib.auth.models import User

usuarios = [
    # (username, password, is_superuser, setor)
    ('ceo_premium', 'Ceo@MasterPremium26!', True, 'Diretoria'),
    ('rh_premium', 'Rh!Premium2026@x9', False, 'Recursos Humanos'),
    ('compras_premium', 'Compras#Eco26$v4', False, 'Compras'),
    ('financeiro_premium', 'Fin@Premium!2026z', False, 'Financeiro'),
    ('sesmet_premium', 'Seg!Trabalho26#w', False, 'SESMET'),
]

for username, password, is_superuser, setor in usuarios:
    # is_staff=True garante que eles consigam entrar no painel de administração (se for usado)
    if not User.objects.filter(username=username).exists():
        user = User.objects.create_user(username=username, password=password)
        user.is_staff = True 
        user.is_superuser = is_superuser
        user.save()
        print(f'[+] Criado usuário: {username} ({setor})')
    else:
        user = User.objects.get(username=username)
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = is_superuser
        user.save()
        print(f'[*] Atualizado usuário existente: {username} ({setor})')
