"""Diagnostico manual da conexao com o armazenamento S3.

Execute diretamente com ``python test_s3_pure.py``. Este modulo nao faz
requisicoes durante a descoberta automatica de testes.
"""
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv


def main():
    load_dotenv('.env')
    endpoint = os.environ.get('SUPABASE_S3_ENDPOINT_URL')
    access_key = os.environ.get('SUPABASE_S3_ACCESS_KEY_ID')
    secret_key = os.environ.get('SUPABASE_S3_SECRET_ACCESS_KEY')
    bucket_name = os.environ.get('SUPABASE_S3_BUCKET_NAME', 'arquivos')
    region = os.environ.get('SUPABASE_S3_REGION_NAME', 'sa-east-1')

    if not all((endpoint, access_key, secret_key, bucket_name)):
        print('Configuracao S3 incompleta.')
        return 2

    # Nunca escreva chaves de acesso no terminal ou em logs.
    print(f'Testando bucket {bucket_name!r} em {endpoint} ({region})...')
    client = boto3.client(
        's3', endpoint_url=endpoint, aws_access_key_id=access_key,
        aws_secret_access_key=secret_key, region_name=region,
    )
    try:
        response = client.list_objects_v2(Bucket=bucket_name, MaxKeys=10)
    except (BotoCoreError, ClientError) as exc:
        print(f'Falha ao acessar o bucket: {exc}')
        return 1

    print(f"Conexao OK; {len(response.get('Contents', []))} objeto(s) listado(s).")
    return 0


if __name__ == '__main__':
    sys.exit(main())
