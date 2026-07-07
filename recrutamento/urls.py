"""ERP Grupo PremiumBR — URLs do Módulo 1: Recrutamento"""
from django.urls import path
from recrutamento import views

urlpatterns = [
    path('', views.lista_vagas, name='lista_vagas'),
    path('nova/', views.nova_vaga, name='nova_vaga'),
    path('<int:pk>/', views.detalhe_vaga, name='detalhe_vaga'),
    path('<int:vaga_pk>/candidato/novo/', views.adicionar_candidato, name='adicionar_candidato'),
    path('candidato/<int:candidato_pk>/avancar/', views.avancar_etapa, name='avancar_etapa'),
    path('banco-talentos/', views.banco_talentos, name='banco_talentos'),
    path('api/parse-curriculo/', views.parse_curriculo, name='parse_curriculo'),
    path('candidato/<int:pk>/baixar-curriculo/', views.baixar_curriculo_candidato, name='baixar_curriculo_candidato'),
    path('talento/<int:pk>/baixar-curriculo/', views.baixar_curriculo_talento, name='baixar_curriculo_talento'),
]
