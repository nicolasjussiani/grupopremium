from django import template
from django.urls import reverse
from admissional.exportacoes import graficos_vt

register = template.Library()
register.simple_tag(graficos_vt)


@register.simple_tag(takes_context=True)
def url_exportar_vt(context, segunda):
    filtros = context['request'].GET.copy()
    filtros['segunda'] = segunda.isoformat()
    return reverse('exportar_vt_xlsx') + '?' + filtros.urlencode()
