from django.urls import path
from . import views

urlpatterns = [
    path('', views.olt_list, name='olt_list'),
    path('add/', views.olt_create, name='olt_create'),
    path('<int:pk>/', views.olt_detail, name='olt_detail'),
    path('<int:pk>/edit/', views.olt_edit, name='olt_edit'),
    path('<int:pk>/delete/', views.olt_delete, name='olt_delete'),
    path('<int:pk>/refresh/', views.olt_refresh, name='olt_refresh'),
    path('<int:pk>/test-connection/', views.olt_test_connection, name='olt_test_connection'),
    path('<int:pk>/metrics-data/', views.olt_metrics_data, name='olt_metrics_data'),
    path('task/<str:task_id>/status/', views.olt_task_status, name='olt_task_status'),
]
