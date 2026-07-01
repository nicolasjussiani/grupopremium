"""ERP Grupo Premium — URLs do Core"""
from django.urls import path
from core import views
from core import views_aprovacao

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('api/notificacoes/', views.notificacoes_json, name='notificacoes_json'),
    path('api/notificacoes/<int:pk>/lida/', views.marcar_notificacao_lida, name='marcar_lida'),

    # ── Linha de Aprovação ──────────────────────────────────────────────────
    path('aprovacoes/', views_aprovacao.aprovacoes_pendentes, name='aprovacoes_pendentes'),
    path('aprovacoes/<int:pk>/aprovar/', views_aprovacao.aprovar_registro, name='aprovar_registro'),
    path('aprovacoes/<int:pk>/rejeitar/', views_aprovacao.rejeitar_registro, name='rejeitar_registro'),
    path('aprovacoes/<int:pk>/detalhe/', views_aprovacao.detalhe_aprovacao, name='detalhe_aprovacao'),
    path('api/aprovacoes/pendentes/count/', views_aprovacao.api_aprovacoes_pendentes_count, name='aprovacoes_count_api'),
    # TEMPORÁRIO: diagnóstico de variáveis de ambiente
    path('debug-env/', views.debug_env, name='debug_env'),
]
