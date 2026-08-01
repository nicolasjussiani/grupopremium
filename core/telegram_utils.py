import os
import requests
import threading

# Mapeamento dos módulos para as respectivas variáveis de ambiente
CONFIG_BOTS = {
    'recrutamento': {
        'token_env': 'TELEGRAM_TOKEN_RECRUTAMENTO',
        'chat_env': 'TELEGRAM_CHAT_ID_RECRUTAMENTO'
    },
    'admissional': {
        'token_env': 'TELEGRAM_TOKEN_ADMISSIONAL',
        'chat_env': 'TELEGRAM_CHAT_ID_ADMISSIONAL'
    },
    'administrativo': {
        'token_env': 'TELEGRAM_TOKEN_ADMINISTRATIVO',
        'chat_env': 'TELEGRAM_CHAT_ID_ADMINISTRATIVO'
    },
    'sesmet': {
        'token_env': 'TELEGRAM_TOKEN_SESMET',
        'chat_env': 'TELEGRAM_CHAT_ID_SESMET'
    },
    # Para módulos que ainda não têm bot específico (compras, financeiro, manutencao)
    # caímos no bot geral/CEO
    'default': {
        'token_env': 'TELEGRAM_BOT_TOKEN',
        'chat_env': 'TELEGRAM_CEO_CHAT_ID'
    }
}

def enviar_mensagem_telegram(modulo, mensagem):
    """
    Envia uma mensagem para o Telegram baseando-se no módulo.
    Roteia para o bot específico da área se existir.
    """
    
    # Verifica se há config específica para o módulo, senão usa o default
    config = CONFIG_BOTS.get(modulo, CONFIG_BOTS['default'])
    
    token = os.environ.get(config['token_env'])
    chat_id = os.environ.get(config['chat_env'])
    
    # Fallback: se não achar o token ou chat_id do módulo específico, tenta o geral
    if not token or not chat_id or chat_id == 'DIGITE_SEU_CHAT_ID_AQUI':
        token = os.environ.get(CONFIG_BOTS['default']['token_env'])
        chat_id = os.environ.get(CONFIG_BOTS['default']['chat_env'])

    if not token or not chat_id or chat_id == 'DIGITE_SEU_CHAT_ID_AQUI':
        print(f"[Telegram] Nenhum Token ou Chat ID configurado para o módulo '{modulo}' nem o default.")
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
                print(f"[Telegram Erro Modulo {modulo}] {response.text}")
        except Exception as e:
            print(f"[Telegram Erro Modulo {modulo}] Falha ao enviar notificação: {e}")

    # Roda em uma thread separada
    threading.Thread(target=_enviar).start()
