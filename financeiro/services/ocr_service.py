import os
import json
from google import genai
from django.conf import settings

def extrair_dados_documento(file_bytes, file_mime_type="application/pdf"):
    """
    Usa o Google Gemini para extrair dados estruturados de um PDF/Imagem.
    Retorna um dicionário com os campos encontrados.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise Exception("Chave da API do Gemini (GEMINI_API_KEY) não configurada.")
    
    client = genai.Client(api_key=api_key)
    
    # Prepara o modelo (gemini-2.5-flash)
    model_name = 'gemini-2.5-flash'
    
    prompt = """
    Você é um assistente financeiro altamente especializado em extração de dados (OCR).
    Leia o documento anexado (nota fiscal, fatura, recibo ou boleto) e extraia as seguintes informações exatamente no formato JSON abaixo.
    Não inclua markdown, crases ou texto extra, apenas o JSON válido.

    ATENÇÃO:
    - O 'valor' deve ser SEMPRE o Valor Total da Nota Fiscal. Não confunda com o valor do Frete ou de impostos parciais.
    - Em Notas Fiscais, a 'razao_social_emitente' geralmente é o nome no topo ou logo após "IDENTIFICAÇÃO DO EMITENTE".
    - O 'numero_documento' geralmente está próximo de 'SÉRIE' no topo à direita.
    - Para 'produtos', faça uma lista de todos os itens detalhados na nota (nome, NCM, qtd, unitário e total).

    Estrutura JSON desejada:
    {
        "cnpj_emitente": "somente numeros ou vazio",
        "razao_social_emitente": "Nome correto da empresa emissora",
        "numero_documento": "Numero da nota ou documento",
        "valor": "valor TOTAL da nota em formato americano (ex: 1500.50), sem cifrao",
        "data_emissao": "AAAA-MM-DD",
        "data_vencimento": "AAAA-MM-DD (se nao houver, tente inferir pela emissao ou use a emissao)",
        "produtos": [
            {
                "descricao_produto": "Nome completo do produto",
                "ncm": "NCM (apenas numeros)",
                "quantidade": "quantidade em formato americano (ex: 1.0 ou 2.5)",
                "valor_unitario": "valor unitario em formato americano",
                "valor_total": "valor total do item em formato americano"
            }
        ]
    }
    """
    
    from google.genai import types
    
    # Configuração de envio do arquivo em inline data
    contents = [
        types.Part.from_bytes(data=file_bytes, mime_type=file_mime_type),
        prompt
    ]
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents
        )
        text_response = response.text.strip()
        
        # Limpar crases Markdown caso o modelo retorne
        if text_response.startswith('```json'):
            text_response = text_response[7:]
        if text_response.startswith('```'):
            text_response = text_response[3:]
        if text_response.endswith('```'):
            text_response = text_response[:-3]
            
        dados_json = json.loads(text_response.strip())
        return dados_json
    except Exception as e:
        print(f"Erro no OCR: {e}")
        raise Exception(f"Falha ao ler o documento com a IA. Motivo: {str(e)}")
