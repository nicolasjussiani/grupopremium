import webview
import subprocess
import time
import socket
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

def wait_for_port(port, host='127.0.0.1', timeout=15):
    """Espera até que a porta especificada esteja aceitando conexões."""
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(0.5)
            if time.time() - start_time > timeout:
                return False

def main():
    # Inicia o servidor Django
    print("Iniciando o servidor do ERP...")
    server_process = subprocess.Popen(
        [sys.executable, str(BASE_DIR / 'manage.py'), 'runserver', '127.0.0.1:8000'],
        cwd=BASE_DIR,
    )
    
    # Aguarda o servidor subir
    if not wait_for_port(8000):
        print("Erro: O servidor demorou muito para iniciar.")
        server_process.terminate()
        return

    # Abre a janela do WebView
    print("Abrindo aplicativo desktop...")
    webview.create_window('ERP Grupo PremiumBR', 'http://127.0.0.1:8000', width=1280, height=800, min_size=(800, 600))
    webview.start()
    
    # Ao fechar a janela, encerra o servidor
    print("Encerrando aplicativo...")
    server_process.terminate()
    try:
        server_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_process.kill()

if __name__ == '__main__':
    main()
