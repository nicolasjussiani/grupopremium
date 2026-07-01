from django.urls import path
from administrativo import views
urlpatterns = [
    path('', views.lista_demandas, name='lista_demandas'),
    path('nova/', views.nova_demanda, name='nova_demanda'),
    path('<int:pk>/', views.detalhe_demanda, name='detalhe_demanda'),
    path('<int:pk>/status/', views.atualizar_status_demanda, name='atualizar_status_demanda'),
]
