from django.db import models
from django.contrib.auth.models import User
from core.utils import format_uptime, STATUS_BADGE


class OLT(models.Model):
    VENDOR_CHOICES = [
        ('ZTE', 'ZTE'),
        ('HUAWEI', 'Huawei'),
    ]
    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('warning', 'Warning'),
        ('unknown', 'Unknown'),
    ]

    name = models.CharField(max_length=100)
    vendor = models.CharField(max_length=20, choices=VENDOR_CHOICES)
    model = models.CharField(max_length=50)
    ip_address = models.GenericIPAddressField()
    telnet_port = models.IntegerField(default=23)
    ssh_port = models.IntegerField(default=22)
    username = models.CharField(max_length=50, default='admin')
    password = models.CharField(max_length=100, default='admin')
    location = models.CharField(max_length=200, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unknown')
    description = models.TextField(blank=True)
    PON_TYPE_CHOICES = [
        ('GPON', 'GPON'),
        ('EPON', 'EPON'),
        ('GPON+EPON', 'GPON+EPON'),
    ]

    snmp_community = models.CharField(max_length=50, default='public')
    snmp_write_community = models.CharField(max_length=50, default='private')
    snmp_port = models.IntegerField(default=161)
    pon_type = models.CharField(max_length=20, choices=PON_TYPE_CHOICES, default='GPON')
    firmware_version = models.CharField(max_length=50, blank=True)
    uptime = models.BigIntegerField(default=0)
    cpu_usage = models.FloatField(default=0)
    memory_usage = models.FloatField(default=0)
    temperature = models.FloatField(default=0)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='olts', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def soft_delete(self):
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.status = 'offline'
        self.save(update_fields=['is_deleted', 'deleted_at', 'status'])

    def __str__(self):
        return f"{self.name} ({self.vendor} {self.model})"

    @property
    def status_badge_class(self):
        return STATUS_BADGE.get(self.status, 'bg-secondary')

    @property
    def vendor_badge_class(self):
        return 'bg-danger' if self.vendor == 'ZTE' else 'bg-primary'

    @property
    def uptime_formatted(self):
        return format_uptime(self.uptime)

    class Meta:
        verbose_name = 'OLT'
        verbose_name_plural = 'OLTs'
        ordering = ['name']


class PONPort(models.Model):
    TECHNOLOGY_CHOICES = [
        ('GPON', 'GPON'),
        ('EPON', 'EPON'),
        ('XGS-PON', 'XGS-PON'),
        ('10G-EPON', '10G-EPON'),
    ]
    STATUS_CHOICES = [
        ('up', 'Up'),
        ('down', 'Down'),
        ('degraded', 'Degraded'),
    ]

    olt = models.ForeignKey(OLT, on_delete=models.CASCADE, related_name='pon_ports')
    board = models.IntegerField(default=1)
    port = models.IntegerField()
    technology = models.CharField(max_length=20, choices=TECHNOLOGY_CHOICES, default='GPON')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='up')
    max_onts = models.IntegerField(default=128)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.olt.name} / Board {self.board} / Port {self.port}"

    @property
    def ont_count(self):
        return self.onts.count()

    @property
    def port_label(self):
        if self.olt.vendor == 'ZTE':
            return f"gpon-onu_{self.board}/{self.port}"
        return f"0/{self.board}/{self.port}"

    @property
    def status_badge_class(self):
        return {
            'up': 'bg-success',
            'down': 'bg-danger',
            'degraded': 'bg-warning text-dark',
        }.get(self.status, 'bg-secondary')

    class Meta:
        ordering = ['olt', 'board', 'port']
        unique_together = ['olt', 'board', 'port']


class DiscoveredONT(models.Model):
    """
    Unregistered ONTs detected on a PON port via SSH auto-discovery.
    Row is deleted once the ONT is registered (an ONT record is created).
    """
    olt = models.ForeignKey(OLT, on_delete=models.CASCADE, related_name='discovered_onts')
    pon_port = models.ForeignKey(PONPort, on_delete=models.CASCADE, related_name='discovered_onts')
    serial_number = models.CharField(max_length=50)
    vendor_info = models.CharField(max_length=100, blank=True)
    discovered_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['pon_port', 'serial_number']
        unique_together = ['pon_port', 'serial_number']

    def __str__(self):
        return f"Discovered {self.serial_number} on {self.pon_port}"
