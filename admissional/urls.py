"""ERP Grupo PremiumBR — URLs do Módulo 2: Admissional"""
from django.urls import path
from admissional import views
from admissional import views_vt
from admissional.exportacoes import exportar_vt

urlpatterns = [
    path('colaboradores/pagamentos/vt-semanal/exportar/', exportar_vt, name='exportar_vt_xlsx'),
    path('', views.lista_admissoes, name='lista_admissoes'),
    path('<int:pk>/', views.detalhe_admissao, name='detalhe_admissao'),
    path('<int:pk>/avancar/', views.avancar_admissao, name='avancar_admissao'),
    path('<int:admissao_pk>/documento/<int:doc_pk>/', views.atualizar_documento, name='atualizar_documento'),
    path('<int:admissao_pk>/documento/<int:doc_pk>/baixar/', views.baixar_documento, name='baixar_documento'),
    path('colaboradores/', views.lista_colaboradores, name='lista_colaboradores'),
    path('colaboradores/novo/', views.novo_colaborador, name='novo_colaborador'),
    path('colaboradores/pagamentos/', views.lista_pagamentos_colaboradores, name='lista_pagamentos_colaboradores'),
    path('colaboradores/pagamentos/relatorio/', views.relatorio_folha_pagamento, name='relatorio_folha_pagamento'),
    path('colaboradores/pagamentos/beneficios/', views.visao_beneficios_colaboradores, name='visao_beneficios_colaboradores'),
    path('colaboradores/pagamentos/vt-semanal/', views_vt.programacao_vt, name='programacao_vt'),
    path('colaboradores/pagamentos/colaborador/<int:pk>/resumo/', views.resumo_colaborador_pagamento, name='resumo_colaborador_pagamento'),
    path('colaboradores/pagamentos/novo/', views.novo_pagamento_colaborador, name='novo_pagamento_colaborador'),
    path('colaboradores/pagamentos/<int:pk>/editar/', views.editar_pagamento_colaborador, name='editar_pagamento_colaborador'),
    path('colaboradores/pagamentos/<int:pk>/marcar-pago/', views.marcar_pagamento_como_pago, name='marcar_pagamento_como_pago'),
    path('colaboradores/pagamentos/<int:pk>/retirar/', views.retirar_pagamento_folha, name='retirar_pagamento_folha'),
    path('colaboradores/<int:pk>/pagamentos/vale-transporte/', views_vt.historico_vt_colaborador, name='historico_vt_colaborador'),
    path('colaboradores/<int:pk>/editar/', views.editar_colaborador, name='editar_colaborador'),
    path('colaboradores/<int:pk>/documentos/', views.documentos_colaborador, name='documentos_colaborador'),
    path('colaboradores/<int:pk>/anexos/<str:campo>/baixar/', views.baixar_anexo_colaborador, name='baixar_anexo_colaborador'),
    path('colaboradores/<int:pk>/documentos/<int:documento_pk>/baixar/', views.baixar_documento_colaborador, name='baixar_documento_colaborador'),
    path('colaboradores/<int:pk>/documentos/<int:documento_pk>/excluir/', views.excluir_documento_colaborador, name='excluir_documento_colaborador'),
    path('colaboradores/<int:pk>/desativar/', views.excluir_colaborador, name='excluir_colaborador'),
    path('colaboradores/<int:pk>/excluir/', views.excluir_colaborador),
    path('colaboradores/<int:pk>/reativar/', views.reativar_colaborador, name='reativar_colaborador'),
    path('colaboradores/presenca/', views.controle_presenca, name='controle_presenca'),
    path('colaboradores/presenca/exportar/', views.exportar_presenca_csv, name='exportar_presenca_csv'),
    path('colaboradores/experiencia/', views.periodo_experiencia, name='periodo_experiencia'),
]
