from django.urls import path
from . import views

urlpatterns = [
    path('pfas', views.list_pfas, name='list-pfas'),
    path('onboard', views.onboard_user, name='onboard-user'),
    path('profile/<uuid:profile_id>', views.get_profile, name='get-profile'),
]
