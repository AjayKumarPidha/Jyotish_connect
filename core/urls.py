from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/',              admin.site.urls),
    path('api/auth/',           include('users.urls')),
    path('api/astrologers/',    include('astrologers.urls')),
    path('api/sessions/',       include('sessions.urls')),
    path('api/wallet/',         include('wallet.urls')),
    path('api/notifications/',  include('notifications.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Jyotish Connect Admin"
admin.site.site_title  = "Jyotish Connect"
admin.site.index_title = "Dashboard"
