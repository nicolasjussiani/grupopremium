from django.urls import path
from financeiro import views
urlpatterns = [
    path('', views.painel_financeiro, name='painel_financeiro'),
    path('documento/novo/', views.entrada_documento, name='entrada_documento'),
    path('documento/<int:pk>/', views.detalhe_documento, name='detalhe_documento'),
    path('documento/<int:pk>/auditoria/', views.auditoria_documento, name='auditoria_documento'),
    path('documento/<int:doc_pk>/lancar/', views.lancar_erp, name='lancar_erp'),
    path('lancamento/<int:pk>/validar/', views.validar_lancamento, name='validar_lancamento'),
    path('documento/<int:pk>/pdf/', views.download_pdf_financeiro, name='download_pdf_financeiro'),
    path('documento/ocr/', views.extrair_ocr_documento, name='extrair_ocr_documento'),
]
