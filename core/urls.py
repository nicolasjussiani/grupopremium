"""ERP Grupo PremiumBR — URLs do Core"""
from django.urls import path
from core import views
from core import views_aprovacao
from core import views_upload

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('ajuda/', views.ajuda, name='ajuda'),
    path('assistente/', views.assistente_erp, name='assistente_erp'),
    path('cadastros/', views.cadastros_gerais, name='cadastros_gerais'),
    path('cadastros/fornecedores/novo/', views.novo_fornecedor, name='novo_fornecedor'),
    path('cadastros/fornecedores/<int:pk>/editar/', views.editar_fornecedor, name='editar_fornecedor'),
    path('cadastros/unidades/nova/', views.nova_unidade, name='nova_unidade'),
    path('cadastros/unidades/<int:pk>/editar/', views.editar_unidade, name='editar_unidade'),
    path('arquivo-central/', views.arquivo_central, name='arquivo_central'),
    path('arquivo-central/<int:pk>/baixar/', views.baixar_arquivo_importado, name='baixar_arquivo_importado'),
    path('arquivo-central/<int:pk>/revisar/', views.revisar_arquivo_importado, name='revisar_arquivo_importado'),
    path('login/', views.login_view, name='login'),
    path('api/csrf/', views.csrf_token_json, name='csrf_token_json'),
    path('logout/', views.logout_view, name='logout'),
    path('api/notificacoes/', views.notificacoes_json, name='notificacoes_json'),
    path('api/notificacoes/<int:pk>/lida/', views.marcar_notificacao_lida, name='marcar_lida'),
    path('api/uploads/presign/', views_upload.presign_upload, name='presign_upload'),
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/novo/', views.novo_usuario, name='novo_usuario'),
    path('usuarios/<int:pk>/editar/', views.editar_usuario, name='editar_usuario'),

    # ── Linha de Aprovação ──────────────────────────────────────────────────
    path('aprovacoes/', views_aprovacao.aprovacoes_pendentes, name='aprovacoes_pendentes'),
    path('aprovacoes/<int:pk>/aprovar/', views_aprovacao.aprovar_registro, name='aprovar_registro'),
    path('aprovacoes/<int:pk>/rejeitar/', views_aprovacao.rejeitar_registro, name='rejeitar_registro'),
    path('aprovacoes/<int:pk>/detalhe/', views_aprovacao.detalhe_aprovacao, name='detalhe_aprovacao'),
    path('api/aprovacoes/pendentes/count/', views_aprovacao.api_aprovacoes_pendentes_count, name='aprovacoes_count_api'),
    path('mobile/', views_aprovacao.painel_mobile, name='painel_mobile'),
    path('mobile/status/', views_aprovacao.status_mobile, name='status_mobile'),
    path('mobile/notificacoes/lidas/', views_aprovacao.marcar_notificacoes_mobile, name='marcar_notificacoes_mobile'),
    path('mobile/notificacoes/teste/', views_aprovacao.criar_notificacao_teste_mobile, name='criar_notificacao_teste_mobile'),
    path('mobile/aprovacoes/<int:pk>/', views_aprovacao.detalhe_aprovacao_mobile, name='detalhe_aprovacao_mobile'),
    path('manifest.webmanifest', views_aprovacao.pwa_manifest, name='pwa_manifest'),
    path('service-worker.js', views_aprovacao.service_worker, name='service_worker'),
    # Auditoria Global (CEO)
    path('auditoria-logs/', views.auditoria_sistema, name='auditoria_sistema'),
    path('diretoria/tempo-processos/', views.painel_sla_processos, name='painel_sla'),
]
