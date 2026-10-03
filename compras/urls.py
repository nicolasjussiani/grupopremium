from django.urls import path
from compras import views
urlpatterns = [
    path('requisicao/<int:pk>/anexo/<str:campo>/remover/', views.remover_anexo_requisicao, name='remover_anexo_requisicao'),
    path('', views.painel_compras, name='painel_compras'),
    path('materiais/', views.lista_materiais, name='lista_materiais'),
    path('materiais/novo/', views.novo_material, name='novo_material'),
    path('materiais/<int:pk>/editar/', views.editar_material, name='editar_material'),
    path('solicitacao/nova/', views.nova_solicitacao, name='nova_solicitacao'),
    path('requisicao/<int:pk>/', views.detalhe_requisicao, name='detalhe_requisicao'),
    path('requisicao/<int:pk>/pedidos/', views.criar_pedidos_requisicao, name='criar_pedidos_requisicao'),
    path('solicitacao/<int:pk>/', views.detalhe_solicitacao, name='detalhe_solicitacao'),
    path('solicitacao/<int:pk>/entrega/', views.confirmar_entrega, name='confirmar_entrega'),
    path('solicitacao/<int:solicitacao_pk>/pedido/', views.criar_pedido_compra, name='criar_pedido'),
    path('pedido/<int:pk>/aprovar/', views.aprovar_pedido, name='aprovar_pedido'),
    path('pedido/<int:pk>/cnpj/', views.atualizar_cnpj_pedido, name='atualizar_cnpj_pedido'),
    path('requisicao/<int:pk>/editar/', views.editar_requisicao, name='editar_requisicao'),
    path('requisicao/<int:pk>/excluir/', views.excluir_requisicao, name='excluir_requisicao'),
]
