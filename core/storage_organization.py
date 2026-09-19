"""Organizacao canonica dos arquivos persistidos no storage."""
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from django.apps import apps
from django.db import transaction


FILE_FIELDS = {
    'core.ArquivoImportado': ('arquivo',),
    'admissional.Colaborador': (
        'anexo_cpf', 'anexo_cpf_verso',
        'anexo_rg', 'anexo_rg_verso',
        'anexo_pis', 'anexo_pis_verso',
        'anexo_ctps', 'anexo_ctps_verso',
        'anexo_titulo', 'anexo_titulo_verso',
        'anexo_reservista', 'anexo_reservista_verso',
        'anexo_aso',
    ),
    'admissional.DocumentoAdmissional': ('arquivo_nuvem',),
    'admissional.DocumentoColaborador': ('arquivo',),
    'recrutamento.Candidato': ('arquivo',),
    'recrutamento.Talento': ('arquivo',),
    'financeiro.DocumentoFinanceiro': ('arquivo',),
    'compras.Material': ('foto',),
    'compras.RequisicaoCompra': ('documento', 'comprovante_pagamento'),
    'sesmet.EquipamentoProtecao': ('foto',),
    'manutencao.Ativo': ('foto',),
    'manutencao.RegistroManutencao': ('foto_equipamento',),
}

ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.xml', '.docx', '.xlsx'}


def _safe_segment(value, fallback):
    value = str(value or '').strip().lower()
    cleaned = ''.join(char for char in value if char.isalnum() or char in '-_')
    return cleaned or fallback


def canonical_prefix(instance, field_name):
    label = instance._meta.label
    if label == 'core.ArquivoImportado':
        digest = _safe_segment(instance.sha256, 'sem_hash')
        return f'arquivo_central/{digest[:2]}/'
    if label == 'admissional.Colaborador':
        return (
            f'admissional/colaboradores/{instance.pk}/documentos/'
            f'{field_name}/'
        )
    if label == 'admissional.DocumentoAdmissional':
        doc_type = _safe_segment(instance.tipo, 'sem_tipo')
        return (
            f'admissional/admissoes/{instance.admissao_id}/documentos/'
            f'{doc_type}/{instance.pk}/'
        )
    if label == 'admissional.DocumentoColaborador':
        doc_type = _safe_segment(instance.tipo, 'sem_tipo')
        return (
            f'admissional/colaboradores/{instance.colaborador_id}/documentos/'
            f'{doc_type}/{instance.pk}/'
        )
    if label == 'recrutamento.Candidato':
        return (
            f'recrutamento/vagas/{instance.vaga_id}/candidatos/'
            f'{instance.pk}/curriculo/'
        )
    if label == 'recrutamento.Talento':
        return f'recrutamento/talentos/{instance.pk}/curriculo/'
    if label == 'financeiro.DocumentoFinanceiro':
        emission = str(instance.data_emissao)
        year = emission[:4] if len(emission) >= 4 else 'sem_ano'
        month = emission[5:7] if len(emission) >= 7 else 'sem_mes'
        doc_type = _safe_segment(instance.tipo, 'sem_tipo')
        return (
            f'financeiro/documentos/{year}/{month}/{instance.pk}/'
            f'{doc_type}/'
        )
    if label == 'compras.Material':
        return f'compras/materiais/{instance.pk}/foto/'
    if label == 'compras.RequisicaoCompra':
        if field_name == 'comprovante_pagamento':
            return f'compras/requisicoes/{instance.pk}/comprovantes/'
        return f'compras/requisicoes/{instance.pk}/documentos/'
    if label == 'sesmet.EquipamentoProtecao':
        return f'sesmet/epis/{instance.pk}/foto/'
    if label == 'manutencao.Ativo':
        return f'manutencao/ativos/{instance.pk}/cadastro/foto/'
    if label == 'manutencao.RegistroManutencao':
        return (
            f'manutencao/ativos/{instance.ativo_id}/registros/'
            f'{instance.pk}/foto/'
        )
    raise ValueError(f'Modelo sem regra de storage: {label}')


def audit_storage_references():
    """Confere se toda referencia do banco existe e usa o prefixo esperado."""
    references = []
    storage_files = {}
    missing = []
    noncanonical = []
    for model_label, field_names in FILE_FIELDS.items():
        model = apps.get_model(model_label)
        for instance in model.objects.iterator():
            for field_name in field_names:
                field_file = getattr(instance, field_name)
                name = field_file.name if field_file else ''
                if not name:
                    continue
                reference = f'{model_label}#{instance.pk}.{field_name}'
                storage = field_file.storage
                references.append((storage, name, reference))
                if not name.startswith(canonical_prefix(instance, field_name)):
                    noncanonical.append(reference)

    # Em S3, uma listagem paginada evita uma requisicao HEAD para cada arquivo.
    # Backends sem listagem eficiente continuam usando exists como fallback.
    for storage, _name, _reference in references:
        storage_id = id(storage)
        if storage_id in storage_files:
            continue
        if getattr(storage, 'bucket_name', None) and getattr(storage, 'connection', None):
            storage_files[storage_id] = set(iter_storage_files(storage))
        else:
            storage_files[storage_id] = None

    for storage, name, reference in references:
        known_names = storage_files[id(storage)]
        exists = name in known_names if known_names is not None else storage.exists(name)
        if not exists:
            missing.append(reference)
    return {
        'total': len(references),
        'missing': missing,
        'noncanonical': noncanonical,
    }


def canonical_key(instance, field_name, source_name):
    extension = Path(source_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = '.bin'
    return f'{canonical_prefix(instance, field_name)}{uuid4().hex}{extension}'


def copy_in_storage(storage, source_name, destination_name):
    """Usa copia interna no S3 e streaming nos demais backends."""
    bucket_name = getattr(storage, 'bucket_name', None)
    connection = getattr(storage, 'connection', None)
    if bucket_name and connection is not None:
        connection.meta.client.copy_object(
            Bucket=bucket_name,
            CopySource={'Bucket': bucket_name, 'Key': source_name},
            Key=destination_name,
        )
        return destination_name

    with storage.open(source_name, 'rb') as source:
        return storage.save(destination_name, source)


def is_referenced(source_name):
    for model_label, field_names in FILE_FIELDS.items():
        model = apps.get_model(model_label)
        for field_name in field_names:
            if model.objects.filter(**{field_name: source_name}).exists():
                return True
    return False


def delete_if_unreferenced(storage, source_name):
    if not is_referenced(source_name):
        storage.delete(source_name)


def organize_instance_files(instance, *, dry_run=False, known_names=None):
    """Move arquivos de uma instancia para seus caminhos canonicos."""
    field_names = FILE_FIELDS.get(instance._meta.label, ())
    if not instance.pk or not field_names:
        return []

    moved = []
    for field_name in field_names:
        field_file = getattr(instance, field_name)
        source_name = field_file.name if field_file else ''
        expected_prefix = canonical_prefix(instance, field_name)
        if not source_name or source_name.startswith(expected_prefix):
            continue

        storage = field_file.storage
        # Referencias legadas podem apontar para um objeto que ja nao existe.
        source_exists = (
            source_name in known_names
            if known_names is not None
            else storage.exists(source_name)
        )
        if not source_exists:
            continue

        destination_name = canonical_key(instance, field_name, source_name)
        moved.append((field_name, source_name, destination_name))
        if dry_run:
            continue

        saved_name = copy_in_storage(storage, source_name, destination_name)
        type(instance).objects.filter(pk=instance.pk).update(
            **{field_name: saved_name}
        )
        getattr(instance, field_name).name = saved_name
        transaction.on_commit(
            lambda storage=storage, source_name=source_name: delete_if_unreferenced(
                storage, source_name
            )
        )

    return moved


def iter_file_models():
    for model_label in FILE_FIELDS:
        yield apps.get_model(model_label)


def referenced_file_names():
    names = set()
    for model_label, field_names in FILE_FIELDS.items():
        model = apps.get_model(model_label)
        for field_name in field_names:
            values = model.objects.exclude(**{field_name: ''}).exclude(
                **{f'{field_name}__isnull': True}
            ).values_list(field_name, flat=True)
            names.update(str(value) for value in values if value)
    return names


def iter_storage_files(storage, path=''):
    bucket_name = getattr(storage, 'bucket_name', None)
    connection = getattr(storage, 'connection', None)
    if bucket_name and connection is not None:
        client = connection.meta.client
        paginator = client.get_paginator('list_objects_v2')
        prefix = path.strip('/')
        if prefix:
            prefix += '/'
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for item in page.get('Contents', ()):
                key = item.get('Key')
                if key and not key.endswith('/'):
                    yield key
        return

    directories, files = storage.listdir(path)
    for filename in files:
        yield f'{path}/{filename}'.lstrip('/')
    for directory in directories:
        child = f'{path}/{directory}'.lstrip('/')
        yield from iter_storage_files(storage, child)


def orphan_quarantine_key(source_name):
    root = _safe_segment(source_name.split('/', 1)[0], 'sem_origem')
    digest = sha256(source_name.encode('utf-8')).hexdigest()[:20]
    extension = Path(source_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = '.bin'
    return f'_orfaos/legado/{root}/{digest}{extension}'


def quarantine_orphaned_files(storage, *, dry_run=False):
    """Move objetos legados sem referencia para uma area recuperavel."""
    referenced = referenced_file_names()
    orphaned = []
    for source_name in iter_storage_files(storage):
        if (
            source_name in referenced
            or source_name.startswith('_orfaos/')
            or source_name.startswith('_temporarios/')
        ):
            continue
        destination_name = orphan_quarantine_key(source_name)
        orphaned.append((source_name, destination_name))
        if dry_run:
            continue
        if not storage.exists(destination_name):
            copy_in_storage(storage, source_name, destination_name)
        storage.delete(source_name)
    return orphaned
