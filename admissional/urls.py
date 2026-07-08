"""ERP Grupo PremiumBR — URLs do Módulo 2: Admissional"""
from django.urls import path
from admissional import views

urlpatterns = [
    path('', views.lista_admissoes, name='lista_admissoes'),
    path('<int:pk>/', views.detalhe_admissao, name='detalhe_admissao'),
    path('<int:pk>/avancar/', views.avancar_admissao, name='avancar_admissao'),
    path('<int:admissao_pk>/documento/<int:doc_pk>/', views.atualizar_documento, name='atualizar_documento'),
    path('<int:admissao_pk>/documento/<int:doc_pk>/baixar/', views.baixar_documento, name='baixar_documento'),
    path('colaboradores/', views.lista_colaboradores, name='lista_colaboradores'),
    path('colaboradores/novo/', views.novo_colaborador, name='novo_colaborador'),
    path('colaboradores/<int:pk>/editar/', views.editar_colaborador, name='editar_colaborador'),
    path('colaboradores/<int:pk>/excluir/', views.excluir_colaborador, name='excluir_colaborador'),
    path('colaboradores/presenca/', views.controle_presenca, name='controle_presenca'),
    path('colaboradores/presenca/exportar/', views.exportar_presenca_csv, name='exportar_presenca_csv'),
    path('colaboradores/experiencia/', views.periodo_experiencia, name='periodo_experiencia'),
]
