"""ERP Grupo Premium — URLs Raiz"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('recrutamento/', include('recrutamento.urls')),
    path('admissional/', include('admissional.urls')),
    path('administrativo/', include('administrativo.urls')),
    path('sesmet/', include('sesmet.urls')),
    path('compras/', include('compras.urls')),
    path('financeiro/', include('financeiro.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
