from django.urls import path

from . import views


urlpatterns = [
    path('', views.painel_fiscal, name='painel_fiscal'),
    path('importar/', views.importar_folha, name='importar_folha_fiscal'),
    path('<int:pk>/', views.detalhe_folha, name='detalhe_folha_fiscal'),
    path('<int:pk>/processar/', views.processar_folha, name='processar_folha_fiscal'),
]
