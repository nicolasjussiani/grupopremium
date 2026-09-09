from django.urls import path
from compras import views
urlpatterns = [
    path('', views.painel_compras, name='painel_compras'),
    path('materiais/', views.lista_materiais, name='lista_materiais'),
    path('materiais/novo/', views.novo_material, name='novo_material'),
    path('materiais/<int:pk>/editar/', views.editar_material, name='editar_material'),
    path('materiais/novo/', views.novo_material, name='novo_material'),
    path('materiais/<int:pk>/editar/', views.editar_material, name='editar_material'),
    path('solicitacao/nova/', views.nova_solicitacao, name='nova_solicitacao'),
    path('solicitacao/<int:pk>/', views.detalhe_solicitacao, name='detalhe_solicitacao'),
    path('solicitacao/<int:solicitacao_pk>/pedido/', views.criar_pedido_compra, name='criar_pedido'),
    path('pedido/<int:pk>/aprovar/', views.aprovar_pedido, name='aprovar_pedido'),
]
