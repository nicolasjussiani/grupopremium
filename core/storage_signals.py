from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from admissional.models import Colaborador, DocumentoAdmissional, DocumentoColaborador
from compras.models import Material
from financeiro.models import DocumentoFinanceiro
from manutencao.models import Ativo, RegistroManutencao
from recrutamento.models import Candidato, Talento
from sesmet.models import EquipamentoProtecao

from .storage_organization import delete_if_unreferenced, organize_instance_files


@receiver(post_save, sender=Colaborador)
@receiver(post_save, sender=DocumentoAdmissional)
@receiver(post_save, sender=DocumentoColaborador)
@receiver(post_save, sender=DocumentoFinanceiro)
@receiver(post_save, sender=Material)
@receiver(post_save, sender=EquipamentoProtecao)
@receiver(post_save, sender=Ativo)
@receiver(post_save, sender=RegistroManutencao)
@receiver(post_save, sender=Candidato)
@receiver(post_save, sender=Talento)
def organize_persisted_uploads(sender, instance, **kwargs):
    organize_instance_files(instance)


@receiver(post_delete, sender=DocumentoColaborador)
def delete_collaborator_document_file(sender, instance, **kwargs):
    name = instance.arquivo.name if instance.arquivo else ''
    if name:
        storage = instance.arquivo.storage
        transaction.on_commit(
            lambda: delete_if_unreferenced(storage, name)
        )
