"""Exclusão de um anexo por vez, preservando o registro ao qual pertence."""
from hashlib import sha256
import logging
from pathlib import PurePosixPath

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from core.access import user_has_access, user_is_executive
from core.models import LogAtividade
from core.storage_organization import FILE_FIELDS, delete_if_unreferenced

logger = logging.getLogger(__name__)
SALT = 'core.excluir-anexo.v1'
PROFILES = {
    'admissional.Colaborador': ('rh', 'sesmet', 'gestor'),
    'admissional.DocumentoColaborador': ('rh', 'sesmet', 'gestor'),
    'admissional.DocumentoAdmissional': ('rh', 'gestor'),
    'admissional.PagamentoColaborador': ('rh', 'financeiro', 'gestor'),
    'recrutamento.Candidato': ('rh', 'gestor'),
    'recrutamento.Talento': ('rh', 'gestor'),
    'financeiro.DocumentoFinanceiro': ('financeiro', 'gestor'),
    'compras.Material': ('compras', 'gestor', 'estoque_compras'),
    'compras.RequisicaoCompra': ('compras', 'gestor', 'estoque_compras'),
    'sesmet.EquipamentoProtecao': ('sesmet', 'gestor', 'estoque_compras'),
    'manutencao.Ativo': ('sesmet', 'compras', 'gestor'),
    'manutencao.RegistroManutencao': ('sesmet', 'compras', 'gestor'),
    'fiscal.FolhaFiscal': ('financeiro', 'gestor'),
}
LEGACY = {
    'admissional.DocumentoAdmissional': 'arquivo',
    'recrutamento.Candidato': 'arquivo_pdf',
    'recrutamento.Talento': 'arquivo_pdf',
    'financeiro.DocumentoFinanceiro': 'arquivo_pdf',
}


def pode_excluir(user, objeto):
    if not user.is_authenticated:
        return False
    if user_is_executive(user):
        return True
    label = objeto._meta.label
    if label == 'core.ArquivoImportado':
        vinculo = objeto.content_object
        if vinculo is not None and vinculo._meta.label in PROFILES:
            return pode_excluir(user, vinculo)
        folha = objeto.folhas_fiscais.first()
        if folha:
            return pode_excluir(user, folha)
        perfis = {
            'rh': ('rh', 'gestor'), 'recrutamento': ('rh', 'gestor'),
            'financeiro': ('financeiro', 'gestor'), 'fiscal': ('financeiro', 'gestor'),
            'compras': ('compras', 'estoque_compras', 'gestor'),
            'sesmet': ('sesmet', 'gestor', 'estoque_compras'),
            'manutencao': ('sesmet', 'compras', 'gestor'), 'administrativo': ('gestor',),
        }.get(objeto.area, ('gestor',))
        return user_has_access(user, permission='core.delete_arquivoimportado', profiles=perfis) or (
            objeto.importado_por_id == user.pk and objeto.area == 'geral'
        )
    if label not in PROFILES:
        return False
    permission = f'{objeto._meta.app_label}.change_{objeto._meta.model_name}'
    if label == 'admissional.DocumentoColaborador':
        permission = 'admissional.change_colaborador'
    return user_has_access(user, permission=permission, profiles=PROFILES[label])


def tem_anexo(objeto, campo):
    if not objeto or not getattr(objeto, 'pk', None):
        return False
    if campo not in FILE_FIELDS.get(objeto._meta.label, ()):
        return False
    return bool(getattr(objeto, campo) or getattr(objeto, LEGACY.get(objeto._meta.label, ''), None))


def referencia(objeto, campo):
    arquivo = getattr(objeto, campo)
    legado = getattr(objeto, LEGACY.get(objeto._meta.label, ''), None)
    return [objeto._meta.label, objeto.pk, campo, arquivo.name or '',
            sha256(bytes(legado)).hexdigest() if legado else '']


def retorno_seguro(request, valor):
    if valor and valor.startswith('/') and url_has_allowed_host_and_scheme(
        valor, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return valor
    return reverse('dashboard')


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def excluir_anexo(request, modelo, pk, campo):
    labels = {label.lower(): label for label in FILE_FIELDS}
    label = labels.get(modelo.lower())
    if not label or campo not in FILE_FIELDS[label]:
        raise Http404
    model = apps.get_model(label)
    retorno = retorno_seguro(request, request.POST.get('next') if request.method == 'POST' else request.GET.get('next'))
    with transaction.atomic():
        objeto = get_object_or_404(model.objects.select_for_update(), pk=pk)
        if not pode_excluir(request.user, objeto):
            raise PermissionDenied
        if not tem_anexo(objeto, campo):
            raise Http404('Este anexo já foi excluído.')
        atual = referencia(objeto, campo)
        arquivo = getattr(objeto, campo)
        nome = getattr(objeto, 'nome_original', '') or getattr(objeto, 'arquivo_nome', '') or PurePosixPath(arquivo.name or '').name or 'Documento anexado'
        contexto = {
            'objeto': objeto, 'nome_anexo': nome, 'campo_label': model._meta.get_field(campo).verbose_name,
            'next': retorno, 'confirmacao': signing.dumps([request.user.pk, atual], salt=SALT),
        }
        if request.method == 'GET':
            return render(request, 'core/excluir_anexo.html', contexto)
        try:
            confirmado = signing.loads(request.POST.get('confirmacao', ''), salt=SALT, max_age=3600)
        except signing.BadSignature:
            confirmado = None
        if confirmado != [request.user.pk, atual]:
            contexto['erro'] = 'O anexo mudou ou a confirmação expirou. Confira o arquivo e confirme novamente.'
            return render(request, 'core/excluir_anexo.html', contexto, status=409)

        storage, name = arquivo.storage, arquivo.name
        # Atualização direta evita reorganizar outros anexos durante esta exclusão.
        changes = {campo: ''}
        legacy = LEGACY.get(label)
        if legacy:
            changes[legacy] = None
        if label == 'admissional.DocumentoAdmissional':
            changes.update(arquivo_nome='', arquivo_mimetype='', status='pendente')
        if label == 'recrutamento.Talento':
            changes['curriculo_texto'] = ''
        model.objects.filter(pk=pk).update(**changes)
        if label == 'admissional.DocumentoColaborador':
            objeto.arquivo.name = ''  # O callback abaixo já cuida do arquivo.
            objeto.delete()
        elif label == 'core.ArquivoImportado':
            if objeto.folhas_fiscais.exists():
                # A folha mantém sua origem e seus valores, mesmo sem o XLSX.
                model.objects.filter(pk=pk).update(texto_extraido='', tamanho=0, motivo_revisao='Anexo excluído pelo usuário.')
            else:
                objeto.delete()
        LogAtividade.objects.create(
            usuario=request.user, acao=f'Excluiu anexo: {campo}', modulo=model._meta.app_label,
            url=request.path, detalhes=f'Registro {label} #{pk}. Arquivo: {nome}'[:1000],
        )
        request._audit_no_change = True  # Auditoria específica acima; não gera notificações.
        if name:
            def limpar_storage():
                try:
                    delete_if_unreferenced(storage, name)
                except Exception:
                    logger.exception('Falha ao limpar anexo removido de %s #%s', label, pk)
                    messages.warning(request, 'O anexo saiu do cadastro, mas a limpeza do armazenamento falhou. Contate o administrador.')
            transaction.on_commit(limpar_storage)
    messages.success(request, 'Anexo excluído. O registro principal foi preservado.')
    return redirect(retorno)
