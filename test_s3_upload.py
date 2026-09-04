"""Diagnostico manual de upload de curriculo para o storage configurado."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_config.settings')
    import django
    django.setup()
    from django.core.files.uploadedfile import SimpleUploadedFile
    from recrutamento.models import Candidato, Vaga

    vaga = Vaga.objects.first()
    if not vaga:
        print('Nenhuma vaga encontrada para o teste.')
        return 2

    candidato = Candidato(
        vaga=vaga, nome='Teste S3', email='teste-s3@example.com',
        telefone='1199999999', cidade='Sao Paulo', cpf_cnpj='000.000.000-00',
    )
    candidato.arquivo = SimpleUploadedFile(
        'teste.pdf', b'%PDF-1.4\nPDF MOCK CONTENT', content_type='application/pdf'
    )
    try:
        candidato.save()
    except Exception as exc:
        print(f'Falha no upload: {exc}')
        return 1

    print(f'Upload concluido: candidato #{candidato.pk}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
