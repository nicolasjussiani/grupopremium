import requests

TOKEN = "8689507800:AAGO2eo1LbkZLMoThOM09l4bqs3uYxwC5jY"
try:
    response = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates").json()
    if response.get("ok") and response.get("result"):
        found = False
        for update in response["result"]:
            if "message" in update:
                chat_id = update["message"]["chat"]["id"]
                user = update["message"]["from"].get("first_name", "Usuário")
                text = update["message"].get("text", "")
                print(f"Chat ID encontrado para {user}: {chat_id} (Mensagem: {text})")
                found = True
        if not found:
            print("Nenhuma mensagem nova encontrada. Mande um 'olá' para o bot e tente novamente.")
    else:
        print("Nenhuma mensagem recebida ou erro.")
except Exception as e:
    print("Erro ao tentar obter atualizações:", e)
