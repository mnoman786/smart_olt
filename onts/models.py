from django.db import models
from olts.models import OLT, PONPort
from core.utils import format_uptime, STATUS_BADGE, SIGNAL_EXCELLENT, SIGNAL_GOOD, SIGNAL_FAIR


class ONTProfile(models.Model):
    PROTOCOL_CHOICES = [
        ('dhcp', 'DHCP'),
        ('pppoe', 'PPPoE'),
        ('static', 'Static IP'),
        ('bridge', 'Bridge'),
    ]
    VENDOR_CHOICES = [
        ('ZTE', 'ZTE'),
        ('HUAWEI', 'Huawei'),
        ('ALL', 'All Vendors'),
    ]

    name = models.CharField(max_length=100)
    vendor = models.CharField(max_length=20, choices=VENDOR_CHOICES, default='ALL')
    download_speed = models.IntegerField(default=100)
    upload_speed = models.IntegerField(default=50)
    protocol = models.CharField(max_length=20, choices=PROTOCOL_CHOICES, default='dhcp')
    vlan_id = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.download_speed}/{self.upload_speed} Mbps)"

    class Meta:
        ordering = ['name']


class ONT(models.Model):
    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('los', 'LOS'),
        ('power_failure', 'Power Failure'),
        ('fiber_cut', 'Fiber Cut'),
        ('degraded', 'Degraded'),
        ('provisioning', 'Provisioning'),
    ]
    MODE_CHOICES = [
        ('routing', 'Routing'),
        ('bridging', 'Bridging'),
    ]
    TECHNOLOGY_CHOICES = [
        ('GPON', 'GPON'),
        ('EPON', 'EPON'),
        ('XGS-PON', 'XGS-PON'),
    ]

    olt = models.ForeignKey(OLT, on_delete=models.CASCADE, related_name='onts')
    pon_port = models.ForeignKey(PONPort, on_delete=models.SET_NULL, related_name='onts', null=True, blank=True)
    ont_id = models.IntegerField(default=1)
    serial_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='offline')
    technology = models.CharField(max_length=20, choices=TECHNOLOGY_CHOICES, default='GPON')
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='routing')

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    mac_address = models.CharField(max_length=17, blank=True)

    rx_power = models.FloatField(default=0)
    tx_power = models.FloatField(default=0)
    olt_rx_power = models.FloatField(default=0)
    distance = models.FloatField(default=0)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    address = models.CharField(max_length=200, blank=True)

    profile = models.ForeignKey(ONTProfile, on_delete=models.SET_NULL, null=True, blank=True)
    vlan = models.IntegerField(default=100)

    uptime = models.BigIntegerField(default=0)
    last_online = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.serial_number})"

    @property
    def signal_quality(self):
        if self.status != 'online':
            return 'unknown'
        if self.rx_power >= SIGNAL_EXCELLENT:
            return 'excellent'
        if self.rx_power >= SIGNAL_GOOD:
            return 'good'
        if self.rx_power >= SIGNAL_FAIR:
            return 'fair'
        return 'poor'

    @property
    def signal_badge_class(self):
        return {
            'excellent': 'bg-success',
            'good': 'bg-success',
            'fair': 'bg-warning text-dark',
            'poor': 'bg-danger',
            'unknown': 'bg-secondary',
        }.get(self.signal_quality, 'bg-secondary')

    @property
    def status_badge_class(self):
        return STATUS_BADGE.get(self.status, 'bg-secondary')

    @property
    def uptime_formatted(self):
        return format_uptime(self.uptime)

    class Meta:
        ordering = ['olt', 'pon_port', 'ont_id']
