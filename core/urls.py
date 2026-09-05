"""ERP Grupo PremiumBR — URLs do Core"""
from django.urls import path
from core import views
from core import views_aprovacao
from core import views_upload

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('api/csrf/', views.csrf_token_json, name='csrf_token_json'),
    path('logout/', views.logout_view, name='logout'),
    path('api/notificacoes/', views.notificacoes_json, name='notificacoes_json'),
    path('api/notificacoes/<int:pk>/lida/', views.marcar_notificacao_lida, name='marcar_lida'),
    path('api/uploads/presign/', views_upload.presign_upload, name='presign_upload'),

    # ── Linha de Aprovação ──────────────────────────────────────────────────
    path('aprovacoes/', views_aprovacao.aprovacoes_pendentes, name='aprovacoes_pendentes'),
    path('aprovacoes/<int:pk>/aprovar/', views_aprovacao.aprovar_registro, name='aprovar_registro'),
    path('aprovacoes/<int:pk>/rejeitar/', views_aprovacao.rejeitar_registro, name='rejeitar_registro'),
    path('aprovacoes/<int:pk>/detalhe/', views_aprovacao.detalhe_aprovacao, name='detalhe_aprovacao'),
    path('api/aprovacoes/pendentes/count/', views_aprovacao.api_aprovacoes_pendentes_count, name='aprovacoes_count_api'),
    path('mobile/', views_aprovacao.painel_mobile, name='painel_mobile'),
    path('mobile/status/', views_aprovacao.status_mobile, name='status_mobile'),
    path('mobile/notificacoes/lidas/', views_aprovacao.marcar_notificacoes_mobile, name='marcar_notificacoes_mobile'),
    path('mobile/aprovacoes/<int:pk>/', views_aprovacao.detalhe_aprovacao_mobile, name='detalhe_aprovacao_mobile'),
    path('manifest.webmanifest', views_aprovacao.pwa_manifest, name='pwa_manifest'),
    path('service-worker.js', views_aprovacao.service_worker, name='service_worker'),
    # Auditoria Global (CEO)
    path('auditoria-logs/', views.auditoria_sistema, name='auditoria_sistema'),
    path('diretoria/tempo-processos/', views.painel_sla_processos, name='painel_sla'),
]
