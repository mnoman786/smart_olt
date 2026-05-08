from django.urls import path
from . import views

urlpatterns = [
    path('', views.olt_list, name='olt_list'),
    path('add/', views.olt_create, name='olt_create'),
    path('<int:pk>/', views.olt_detail, name='olt_detail'),
    path('<int:pk>/snmp-live/', views.olt_snmp_live, name='olt_snmp_live'),
    path('<int:pk>/snmp-unregistered/', views.olt_snmp_unregistered, name='olt_snmp_unregistered'),
    path('<int:olt_pk>/pon/<int:pon_pk>/snmp-live/', views.pon_snmp_live, name='pon_snmp_live'),
    path('<int:pk>/setup-commands/', views.olt_setup_commands, name='olt_setup_commands'),
    path('<int:pk>/edit/', views.olt_edit, name='olt_edit'),
    path('<int:pk>/delete/', views.olt_delete, name='olt_delete'),
    path('<int:pk>/refresh/', views.olt_refresh, name='olt_refresh'),
    path('<int:pk>/test-connection/', views.olt_test_connection, name='olt_test_connection'),
    path('test-connection/', views.olt_test_connection_raw, name='olt_test_connection_raw'),
    path('<int:pk>/metrics-data/', views.olt_metrics_data, name='olt_metrics_data'),
    path('task/<str:task_id>/status/', views.olt_task_status, name='olt_task_status'),
    path('<int:olt_pk>/pon/<int:pon_pk>/', views.pon_detail, name='pon_detail'),
    path('<int:olt_pk>/pon/<int:pon_pk>/scan/', views.scan_pon_port, name='scan_pon_port'),
    path('<int:pk>/scan-all/', views.scan_olt_all_ports, name='scan_olt_all_ports'),
    path('<int:pk>/sync-device/', views.sync_olt_device, name='sync_olt_device'),
    path('super-admin/', views.super_admin_dashboard, name='super_admin_dashboard'),
    path('<int:pk>/diag/', views.olt_diag, name='olt_diag'),
]
