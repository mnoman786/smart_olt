from django.db import models
from olts.models import OLT
from onts.models import ONT


class SignalHistory(models.Model):
    ont = models.ForeignKey(ONT, on_delete=models.CASCADE, related_name='signal_history')
    timestamp = models.DateTimeField()
    rx_power = models.FloatField()
    tx_power = models.FloatField()
    olt_rx_power = models.FloatField()

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['ont', '-timestamp'])]


class TrafficHistory(models.Model):
    ont = models.ForeignKey(ONT, on_delete=models.CASCADE, related_name='traffic_history')
    timestamp = models.DateTimeField()
    download_mbps = models.FloatField()
    upload_mbps = models.FloatField()

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['ont', '-timestamp'])]


class OLTMetrics(models.Model):
    olt = models.ForeignKey(OLT, on_delete=models.CASCADE, related_name='metrics')
    timestamp = models.DateTimeField()
    cpu_usage = models.FloatField()
    memory_usage = models.FloatField()
    temperature = models.FloatField()

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['olt', '-timestamp'])]


class Event(models.Model):
    TYPE_CHOICES = [
        ('online', 'ONT Online'),
        ('offline', 'ONT Offline'),
        ('los', 'Loss of Signal'),
        ('power_failure', 'Power Failure'),
        ('fiber_cut', 'Fiber Cut'),
        ('signal_degraded', 'Signal Degraded'),
        ('olt_online', 'OLT Online'),
        ('olt_offline', 'OLT Offline'),
        ('provisioned', 'ONT Provisioned'),
        ('rebooted', 'ONT Rebooted'),
        ('factory_reset', 'Factory Reset'),
    ]
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info')
    olt = models.ForeignKey(OLT, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    ont = models.ForeignKey(ONT, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)

    def __str__(self):
        return f"[{self.severity.upper()}] {self.message[:60]}"

    @property
    def severity_badge_class(self):
        return {
            'info': 'bg-info',
            'warning': 'bg-warning text-dark',
            'critical': 'bg-danger',
        }.get(self.severity, 'bg-secondary')

    @property
    def severity_icon(self):
        return {
            'info': 'fa-circle-info',
            'warning': 'fa-triangle-exclamation',
            'critical': 'fa-circle-xmark',
        }.get(self.severity, 'fa-circle')

    class Meta:
        ordering = ['-timestamp']
