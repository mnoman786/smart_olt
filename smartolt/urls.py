from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('olts/', include('olts.urls')),
    path('onts/', include('onts.urls')),
    path('monitoring/', include('monitoring.urls')),
    path('alerts/', include('alerts.urls')),
    path('reports/', include('reports.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
