import os
import re
import io

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

def extrair_dados_documento(file_bytes, file_mime_type="application/pdf"):
    """
    Usa PyMuPDF e Tesseract para extrair texto e Regex para buscar as informações.
    Retorna um dicionário com os campos encontrados.
    """
    if not HAS_FITZ:
        raise Exception("Biblioteca de leitura de PDF (PyMuPDF) não está instalada no servidor.")
        
    texto = ""
    try:
        if file_mime_type == "application/pdf":
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                page_text = page.get_text()
                if len(page_text.strip()) > 5:
                    texto += page_text + "\n"
                else:
                    if HAS_OCR:
                        try:
                            pix = page.get_pixmap(dpi=150)
                            img = Image.open(io.BytesIO(pix.tobytes()))
                            texto += pytesseract.image_to_string(img, lang='por') + "\n"
                        except Exception as ocr_e:
                            print(f"OCR ignorado na página: {ocr_e}")
            doc.close()
        else:
            if HAS_OCR:
                img = Image.open(io.BytesIO(file_bytes))
                texto = pytesseract.image_to_string(img, lang='por')
    except Exception as e:
        print(f"Erro na extração de texto: {e}")
        raise Exception(f"Falha ao processar o arquivo: {str(e)}")

    # 1. Extrair CNPJ (primeiro encontrado costuma ser do emissor na maioria dos layouts se for NF-e)
    cnpj_match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)
    cnpj = cnpj_match.group(0) if cnpj_match else ""

    # 2. Extrair Número da NF (Nº 000.000.000 ou Numero: 12345)
    numero_match = re.search(r'(?:Nº|No|Número|Numero|NF-e)\s*[:\-\.]?\s*0*(\d{4,9})', texto, re.IGNORECASE)
    numero = numero_match.group(1) if numero_match else ""

    # 3. Extrair Data de Emissão (DD/MM/AAAA)
    data_match = re.search(r'(\d{2})[-/](\d{2})[-/](\d{4})', texto)
    data_emissao = ""
    if data_match:
        dia, mes, ano = data_match.groups()
        data_emissao = f"{ano}-{mes}-{dia}" # Formato AAAA-MM-DD exigido pelo HTML

    # 4. Extrair Valor Total (VALOR TOTAL DA NOTA 1.500,00 ou TOTAL: R$ 1.500,00)
    # Busca um número no padrão 1.234,56 ou 1234,56
    valor_match = re.search(r'(?:TOTAL(?: DA NOTA)?|VALOR(?: TOTAL)?)[^\d]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE)
    valor = ""
    if valor_match:
        # Converter 1.500,00 para 1500.50
        valor = valor_match.group(1).replace('.', '').replace(',', '.')

    # 5. Tentar pegar a Razão Social (geralmente primeira linha antes do CNPJ ou texto grande no topo)
    # Muito difícil via Regex puro sem ancoras, deixamos em branco para a pessoa conferir, ou pegamos a primeira linha válida
    razao_social = ""
    linhas = texto.split('\n')
    for linha in linhas:
        linha = linha.strip()
        if len(linha) > 5 and not re.search(r'\d', linha) and not 'RECEBEMOS' in linha.upper():
            razao_social = linha[:50]
            break

    dados_json = {
        "cnpj_emitente": cnpj,
        "razao_social_emitente": razao_social,
        "numero_documento": numero,
        "valor": valor,
        "data_emissao": data_emissao,
        "data_vencimento": data_emissao # Fallback para vencimento
    }

    return dados_json
