import os
import json
import logging
import re
from datetime import datetime
from django.conf import settings


logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def _extrair_localmente(file_bytes, file_mime_type):
    """Fallback conservador para PDFs com texto, sem uso de API externa."""
    texto = ''
    if file_mime_type == 'application/pdf':
        try:
            import pymupdf
            with pymupdf.open(stream=file_bytes, filetype='pdf') as documento:
                texto = '\n'.join(pagina.get_text() for pagina in documento)[:50000]
        except Exception:
            logger.info('PDF sem texto extraivel no modo local', exc_info=True)

    def primeiro(padroes):
        for padrao in padroes:
            encontrado = re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)
            if encontrado:
                return encontrado.group(1).strip()
        return ''

    def data_iso(valor):
        for formato in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(valor, formato).date().isoformat()
            except (TypeError, ValueError):
                continue
        return ''

    valor = primeiro([
        r'VALOR\s+TOTAL\s+DA\s+NOTA[^\d]*(\d[\d.]*,\d{2})',
        r'VALOR\s+TOTAL[^\d]*(\d[\d.]*,\d{2})',
        r'R\$\s*(\d[\d.]*,\d{2})',
    ])
    if valor:
        valor = valor.replace('.', '').replace(',', '.')
    emissao = primeiro([r'(?:DATA\s+DE\s+)?EMISS[AÃ]O\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})'])
    vencimento = primeiro([r'VENCIMENTO\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})'])
    dados = {
        'cnpj_emitente': primeiro([r'CNPJ(?:/CPF)?\s*[:\-]?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})']),
        'razao_social_emitente': primeiro([
            r'RAZ[AÃ]O\s+SOCIAL\s*[:\-]?\s*([^\r\n]{3,200})',
            r'IDENTIFICA[CÇ][AÃ]O\s+DO\s+EMITENTE\s*[\r\n]+\s*([^\r\n]{3,200})',
        ]),
        'numero_documento': primeiro([
            r'(?:N[UÚ]MERO|N[º°O])\s*(?:DA\s+NF(?:-E)?)?\s*[:#-]?\s*(\d{1,20})',
            r'NF(?:-E)?\s*[:#-]?\s*(\d{1,20})',
        ]),
        'valor': valor,
        'data_emissao': data_iso(emissao),
        'data_vencimento': data_iso(vencimento),
        'produtos': [],
        '_modo': 'local',
        '_aviso': (
            'Leitura provisoria por regras locais. Confira todos os campos antes de salvar.'
            if texto else
            'Nao foi possivel ler o texto sem a chave da IA. Confira os campos manualmente.'
        ),
    }
    return dados

def extrair_dados_documento(file_bytes, file_mime_type="application/pdf"):
    """
    Usa o Google Gemini para extrair dados estruturados de um PDF/Imagem.
    Retorna um dicionário com os campos encontrados.
    """
    if False and not HAS_GENAI:
        raise Exception("Biblioteca 'google-genai' não está instalada ou falhou ao carregar.")
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not HAS_GENAI or not api_key:
        return _extrair_localmente(file_bytes, file_mime_type)
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
    except Exception as exc:
        logger.exception('Falha no servico de OCR')
        raise RuntimeError('Falha ao ler o documento com a IA.') from exc
