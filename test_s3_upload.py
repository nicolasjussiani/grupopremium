import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
django.setup()

from recrutamento.models import Candidato, Vaga
from django.core.files.uploadedfile import SimpleUploadedFile

vaga = Vaga.objects.first()
if not vaga:
    print("Nenhuma vaga encontrada para o teste.")
    exit()

print(f"Usando a vaga: {vaga.nome_vaga}")

candidato = Candidato(
    vaga=vaga,
    nome="Teste S3",
    email="teste@s3.com",
    telefone="1199999999",
)

file_bytes = b"PDF MOCK CONTENT"
upload = SimpleUploadedFile("teste.pdf", file_bytes, content_type="application/pdf")

candidato.arquivo = upload
candidato.arquivo_pdf = file_bytes

try:
    print("Tentando salvar...")
    candidato.save()
    print("Salvo com sucesso!")
except Exception as e:
    import traceback
    traceback.print_exc()
