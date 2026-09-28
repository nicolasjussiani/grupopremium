from urllib.parse import urlencode
from django import template
from django.urls import reverse
from django.utils.html import format_html
from core.anexos import pode_excluir, tem_anexo

register = template.Library()


@register.simple_tag(takes_context=True)
def excluir_anexo(context, objeto, campo='arquivo'):
    request = context.get('request')
    if not request or not tem_anexo(objeto, campo) or not pode_excluir(request.user, objeto):
        return ''
    url = reverse('excluir_anexo', args=[objeto._meta.label_lower, objeto.pk, campo])
    next_url = request.get_full_path()
    if objeto._meta.label == 'core.ArquivoImportado' and request.path in (
        reverse('detalhe_arquivo_importado', args=[objeto.pk]),
        reverse('revisar_arquivo_importado', args=[objeto.pk]),
    ):
        next_url = reverse('arquivo_central')
    url += '?' + urlencode({'next': next_url})
    return format_html('<a href="{}" class="btn btn-sm btn-danger" style="margin:4px;" data-excluir-anexo>Excluir anexo</a>', url)
