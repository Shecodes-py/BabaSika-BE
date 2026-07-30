from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('accounts.urls')),
    path('api/v1/', include('payments.urls')),
    path('api/v1/', include('bmoni.urls')),
    path("bot/", include("bot.urls")),
]
