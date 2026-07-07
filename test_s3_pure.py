import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv('.env')

endpoint = os.environ.get('SUPABASE_S3_ENDPOINT_URL')
access_key = os.environ.get('SUPABASE_S3_ACCESS_KEY_ID')
secret_key = os.environ.get('SUPABASE_S3_SECRET_ACCESS_KEY')
bucket_name = os.environ.get('SUPABASE_S3_BUCKET_NAME', 'arquivos')
region = os.environ.get('SUPABASE_S3_REGION_NAME', 'sa-east-1') # Pode ser que a sua região seja us-east-1

print("="*50)
print(f"Endpoint: {endpoint}")
print(f"Access Key: {access_key}")
print(f"Bucket: {bucket_name}")
print(f"Região atual configurada: {region}")
print("="*50)

s3_client = boto3.client(
    's3',
    endpoint_url=endpoint,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name=region
)

try:
    print("Testando leitura do Bucket...")
    # Testa se o bucket existe e lista os arquivos (equivale ao HeadObject)
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    print("\n✅ SUCESSO! Acesso liberado ao Bucket!")
    arquivos = [obj['Key'] for obj in response.get('Contents', [])]
    print(f"Arquivos lá dentro: {arquivos}")
except ClientError as e:
    print("\n❌ ERRO S3 (Acesso Negado ou Região Incorreta):")
    print(e)
    print("\n DICA: Se o erro for 403 Forbidden, experimente mudar a região para 'us-east-1' no arquivo .env e rode o script de novo!")
