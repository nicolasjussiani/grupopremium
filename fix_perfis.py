import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import PerfilUsuario

perfis_map = {
    'ceo_premium': 'gestor',
    'rh_premium': 'rh',
    'compras_premium': 'compras',
    'financeiro_premium': 'financeiro',
    'sesmet_premium': 'sesmet',
}

for username, perfil_nome in perfis_map.items():
    try:
        user = User.objects.get(username=username)
        perfil, created = PerfilUsuario.objects.get_or_create(
            usuario=user,
            defaults={'perfil': perfil_nome, 'marca': 'eco_premium', 'unidade': 'Matriz'}
        )
        if not created:
            perfil.perfil = perfil_nome
            perfil.save()
        print(f"[OK] Perfil '{perfil_nome}' vinculado ao usuario {username} com sucesso!")
    except User.DoesNotExist:
        print(f"[ERROR] Usuario {username} nao encontrado.")
