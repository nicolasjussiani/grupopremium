from django.contrib import admin
from .models import Vaga, Candidato

@admin.register(Vaga)
class VagaAdmin(admin.ModelAdmin):
    list_display = ['nome_vaga', 'unidade', 'cidade', 'tipo_contratacao', 'status', 'criado_em']
    list_filter = ['status', 'tipo_contratacao', 'unidade']
    search_fields = ['nome_vaga', 'gestor_responsavel']

@admin.register(Candidato)
class CandidatoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'vaga', 'etapa_atual', 'aprovado', 'encaminhado_admissao']
    list_filter = ['etapa_atual', 'aprovado']
