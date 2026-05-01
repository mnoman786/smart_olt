from django.urls import path
from . import views

urlpatterns = [
    path('rules/', views.rules_list, name='rules_list'),
    path('rules/create/', views.rule_create, name='rule_create'),
    path('rules/<int:pk>/edit/', views.rule_edit, name='rule_edit'),
    path('rules/<int:pk>/delete/', views.rule_delete, name='rule_delete'),
    path('history/', views.notification_history, name='alert_history'),
]
