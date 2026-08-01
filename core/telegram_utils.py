import os
import requests
import threading

def enviar_mensagem_telegram(mensagem):
    """
    Envia uma mensagem para o CEO via Telegram de forma assíncrona.
    """
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CEO_CHAT_ID')

    if not token or not chat_id or chat_id == 'DIGITE_SEU_CHAT_ID_AQUI':
        print("[Telegram] Token ou Chat ID não configurados adequadamente.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem,
        "parse_mode": "HTML"
    }

    def _enviar():
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code != 200:
                print(f"[Telegram Erro] {response.text}")
        except Exception as e:
            print(f"[Telegram Erro] Falha ao enviar notificação: {e}")

    # Roda em uma thread separada para não travar a requisição do usuário
    threading.Thread(target=_enviar).start()
