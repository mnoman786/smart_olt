from django.urls import path
from . import views

urlpatterns = [
    path('', views.reports_index, name='reports'),
    path('export/', views.export_csv, name='reports_export'),
]
