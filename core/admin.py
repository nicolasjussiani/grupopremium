from django.contrib import admin
from .models import PerfilUsuario, Notificacao, AprovacaoRegistro

@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'perfil', 'marca', 'unidade']
    list_filter = ['perfil', 'marca']

@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ['destinatario', 'tipo', 'modulo', 'titulo', 'lida', 'criado_em']
    list_filter = ['tipo', 'modulo', 'lida']

@admin.register(AprovacaoRegistro)
class AprovacaoRegistroAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'modulo', 'nivel', 'status', 'solicitado_por', 'aprovado_por', 'criado_em', 'decidido_em']
    list_filter = ['modulo', 'nivel', 'status']
    search_fields = ['titulo', 'descricao', 'solicitado_por__username', 'aprovado_por__username']
    readonly_fields = ['criado_em', 'decidido_em', 'content_type', 'object_id']
    date_hierarchy = 'criado_em'
    ordering = ['-criado_em']

