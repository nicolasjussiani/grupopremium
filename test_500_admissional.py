import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
import traceback

try:
    client = Client()
    user = User.objects.filter(username='test_no_perfil').first()
    client.force_login(user)

    print("Requesting GET /admissional/colaboradores/novo/")
    response = client.get('/admissional/colaboradores/novo/')
    print(f"Status Code: {response.status_code}")
    if response.status_code == 302:
        print(f"Redirect URL: {response.url}")
except Exception as e:
    traceback.print_exc()
