from django.urls import path
from sesmet import views
urlpatterns = [
    path('', views.dashboard_sesmet, name='dashboard_sesmet'),
    path('epi/registrar/', views.registrar_epi, name='registrar_epi'),
    path('epi/registrar/<int:colaborador_pk>/', views.registrar_epi, name='registrar_epi_colaborador'),
    path('epi/<int:epi_pk>/assinar/', views.assinar_epi, name='assinar_epi'),
    path('epi/<int:epi_pk>/recibo/', views.recibo_epi, name='recibo_epi'),
    path('matriz/', views.matriz_epis, name='matriz_epis'),
    path('os/<int:colaborador_pk>/', views.emitir_os, name='emitir_os'),
    
    # Novas rotas para o Catálogo de Equipamentos
    path('catalogo/', views.catalogo_equipamentos, name='catalogo_equipamentos'),
    path('catalogo/novo/', views.novo_equipamento, name='novo_equipamento'),
    path('catalogo/<int:pk>/editar/', views.editar_equipamento, name='editar_equipamento'),
]
