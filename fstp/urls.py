from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

handler404 = 'trk.views.error_404'
handler500 = 'trk.views.error_500'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('trk.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
