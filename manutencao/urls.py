from django.urls import path
from . import views

urlpatterns = [
    path('', views.painel_manutencao, name='painel_manutencao'),
    path('ativos/', views.lista_ativos, name='lista_ativos'),
    path('ativos/novo/', views.novo_ativo, name='novo_ativo'),
    path('ativos/editar/<int:pk>/', views.editar_ativo, name='editar_ativo'),
    path('chamados/', views.lista_manutencoes, name='lista_manutencoes'),
    path('chamados/novo/', views.nova_manutencao, name='nova_manutencao'),
    path('chamados/concluir/<int:pk>/', views.concluir_manutencao, name='concluir_manutencao'),
]
