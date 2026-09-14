"""ERP Grupo PremiumBR — URLs Raiz"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

handler403 = 'core.views.permission_denied_view'
handler404 = 'core.views.page_not_found_view'
handler500 = 'core.views.server_error_view'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('recrutamento/', include('recrutamento.urls')),
    path('admissional/', include('admissional.urls')),
    path('administrativo/', include('administrativo.urls')),
    path('sesmet/', include('sesmet.urls')),
    path('compras/', include('compras.urls')),
    path('financeiro/', include('financeiro.urls')),
    path('manutencao/', include('manutencao.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
