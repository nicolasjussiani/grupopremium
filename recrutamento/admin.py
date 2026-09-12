from django.contrib import admin
from .models import Candidato, HistoricoVaga, Vaga

@admin.register(Vaga)
class VagaAdmin(admin.ModelAdmin):
    list_display = ['nome_vaga', 'unidade', 'cidade', 'tipo_contratacao', 'status', 'criado_em']
    list_filter = ['status', 'tipo_contratacao', 'unidade']
    search_fields = ['nome_vaga', 'gestor_responsavel']

@admin.register(Candidato)
class CandidatoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'vaga', 'etapa_atual', 'aprovado', 'encaminhado_admissao']
    list_filter = ['etapa_atual', 'aprovado']


@admin.register(HistoricoVaga)
class HistoricoVagaAdmin(admin.ModelAdmin):
    list_display = ['nome_vaga', 'acao', 'motivo', 'realizado_por', 'criado_em']
    list_filter = ['acao', 'motivo', 'criado_em']
    search_fields = ['nome_vaga', 'justificativa', 'realizado_por__username']
    readonly_fields = [
        'vaga', 'vaga_id_original', 'nome_vaga', 'acao', 'motivo',
        'justificativa', 'dados_anteriores', 'dados_novos',
        'candidatos_afetados', 'realizado_por', 'criado_em',
    ]
