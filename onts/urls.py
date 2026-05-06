from django.urls import path
from . import views

urlpatterns = [
    path('', views.ont_list, name='ont_list'),
    path('add/', views.ont_create, name='ont_create'),
    path('profiles/', views.profile_list, name='ont_profiles'),
    path('profiles/add/', views.profile_create, name='profile_create'),
    path('profiles/<int:pk>/edit/', views.profile_edit, name='profile_edit'),
    path('profiles/<int:pk>/delete/', views.profile_delete, name='profile_delete'),
    path('<int:pk>/', views.ont_detail, name='ont_detail'),
    path('<int:pk>/edit/', views.ont_edit, name='ont_edit'),
    path('<int:pk>/delete/', views.ont_delete, name='ont_delete'),
    path('<int:pk>/reboot/', views.ont_reboot, name='ont_reboot'),
    path('<int:pk>/factory-reset/', views.ont_factory_reset, name='ont_factory_reset'),
    path('<int:pk>/signal-data/', views.ont_signal_data, name='ont_signal_data'),
    path('<int:pk>/traffic-data/', views.ont_traffic_data, name='ont_traffic_data'),
]
