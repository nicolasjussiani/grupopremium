import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
import traceback

try:
    client = Client()
    user = User.objects.first()
    if user:
        client.force_login(user)
    else:
        print("No users found.")

    response = client.get('/manutencao/ativos/novo/')
    print(f"Status Code: {response.status_code}")
    if response.status_code >= 500:
        print("Response Content:")
        print(response.content.decode('utf-8', errors='ignore'))
except Exception as e:
    traceback.print_exc()
