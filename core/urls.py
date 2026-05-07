from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),  # kept for named URL compatibility
    path('api/stats/', views.api_stats, name='api_stats'),
]
