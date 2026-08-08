import os
import django
from django.utils import timezone
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import AprovacaoRegistro
from django.contrib.contenttypes.models import ContentType

def run_tests():
    print("Iniciando testes de disparo para os 4 módulos recém-cadastrados...\n")
    
    # Usuário solicitante genérico
    solicitante = User.objects.first()
    
    # Tipo de conteúdo genérico só para preencher o campo obrigatório
    ct = ContentType.objects.get_for_model(User)

    modulos_para_testar = [
        ('recrutamento', 'Vaga de Analista Teste'),
        ('admissional', 'Admissão de João Silva'),
        ('administrativo', 'Compra de Material de Escritório'),
        ('sesmet', 'Aprovação de EPI - Capacete Teste')
    ]

    for modulo, titulo in modulos_para_testar:
        print(f"-> Testando disparo para o módulo: {modulo.upper()}")
        
        # Cria a aprovação, o que dispara o signal (e envia pro Telegram no thread)
        aprovacao = AprovacaoRegistro.objects.create(
            content_type=ct,
            object_id=solicitante.id,
            modulo=modulo,
            nivel=1,
            titulo=titulo,
            descricao=f"Este é um teste automatizado do sistema ERP para a área de {modulo}.",
            solicitado_por=solicitante,
            status='pendente'
        )
        print(f"   Aprovação '{titulo}' gerada!")
        
        # Pausa breve para dar tempo da thread HTTP rodar
        time.sleep(1.5)
        
        # Após o teste, vamos deletar o registro para não poluir o banco real do cliente
        aprovacao.delete()
    print("\n[OK] Testes concluídos! Verifique o seu Telegram.")

if __name__ == '__main__':
    run_tests()
