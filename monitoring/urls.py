from django.urls import path
from . import views

urlpatterns = [
    path('signals/', views.signals_view, name='monitoring_signals'),
    path('traffic/', views.traffic_view, name='monitoring_traffic'),
    path('events/', views.events_view, name='monitoring_events'),
    path('events/<int:pk>/acknowledge/', views.acknowledge_event, name='acknowledge_event'),
    path('api/signals-chart/', views.signals_chart_data, name='signals_chart_data'),
    path('api/traffic-chart/', views.traffic_chart_data, name='traffic_chart_data'),
]
