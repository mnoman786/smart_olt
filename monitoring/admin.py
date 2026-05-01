from django.contrib import admin
from .models import SignalHistory, TrafficHistory, OLTMetrics, Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['type', 'severity', 'olt', 'ont', 'message', 'timestamp', 'acknowledged']
    list_filter = ['severity', 'type', 'acknowledged']
    search_fields = ['message']
    date_hierarchy = 'timestamp'


@admin.register(SignalHistory)
class SignalHistoryAdmin(admin.ModelAdmin):
    list_display = ['ont', 'timestamp', 'rx_power', 'tx_power', 'olt_rx_power']
    list_filter = ['ont']


@admin.register(TrafficHistory)
class TrafficHistoryAdmin(admin.ModelAdmin):
    list_display = ['ont', 'timestamp', 'download_mbps', 'upload_mbps']


@admin.register(OLTMetrics)
class OLTMetricsAdmin(admin.ModelAdmin):
    list_display = ['olt', 'timestamp', 'cpu_usage', 'memory_usage', 'temperature']
