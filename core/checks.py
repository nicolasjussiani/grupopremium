from django.apps import apps
from django.core.checks import Error, Tags, register
from django.db.models import FileField

from core.storage_organization import FILE_FIELDS


LOCAL_APPS = {
    'admissional', 'recrutamento', 'financeiro', 'manutencao', 'compras', 'sesmet',
}


@register(Tags.models)
def check_file_fields_are_organized(app_configs, **kwargs):
    """Falha cedo se um novo arquivo puder ser salvo fora da arquitetura."""
    errors = []
    covered = {
        (model_label, field_name)
        for model_label, field_names in FILE_FIELDS.items()
        for field_name in field_names
    }
    for model in apps.get_models():
        if model._meta.app_label not in LOCAL_APPS:
            continue
        for field in model._meta.fields:
            if isinstance(field, FileField) and (model._meta.label, field.name) not in covered:
                errors.append(Error(
                    f'{model._meta.label}.{field.name} nao possui regra de organizacao no Storage.',
                    hint='Adicione o campo em core.storage_organization.FILE_FIELDS e defina canonical_prefix().',
                    id='core.E001',
                ))
    return errors
