from django.contrib import admin

from .models import BeneficioFiscal, FolhaFiscal, ItemFolhaFiscal, ParcelaBeneficioFiscal


class ItemFolhaFiscalInline(admin.TabularInline):
    model = ItemFolhaFiscal
    extra = 0
    show_change_link = True


@admin.register(FolhaFiscal)
class FolhaFiscalAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'competencia', 'versao', 'status', 'criado_em')
    list_filter = ('status', 'competencia')
    search_fields = ('titulo', 'hash_origem')
    inlines = (ItemFolhaFiscalInline,)


@admin.register(ItemFolhaFiscal)
class ItemFolhaFiscalAdmin(admin.ModelAdmin):
    list_display = ('nome_fonte', 'regime', 'folha', 'status_conciliacao', 'status_fonte')
    list_filter = ('regime', 'status_conciliacao', 'status_fonte')
    search_fields = ('nome_fonte', 'cpf_cnpj_fonte', 'contrato', 'unidade')


admin.site.register(BeneficioFiscal)
admin.site.register(ParcelaBeneficioFiscal)
