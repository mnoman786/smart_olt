from django.db import models


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
    snmp_community = models.CharField(max_length=50, default='public')
    firmware_version = models.CharField(max_length=50, blank=True)
    uptime = models.BigIntegerField(default=0)
    cpu_usage = models.FloatField(default=0)
    memory_usage = models.FloatField(default=0)
    temperature = models.FloatField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.vendor} {self.model})"

    @property
    def ont_count(self):
        return self.onts.count()

    @property
    def online_ont_count(self):
        return self.onts.filter(status='online').count()

    @property
    def offline_ont_count(self):
        return self.onts.filter(status__in=['offline', 'los', 'power_failure', 'fiber_cut']).count()

    @property
    def status_badge_class(self):
        return {
            'online': 'bg-success',
            'offline': 'bg-danger',
            'warning': 'bg-warning text-dark',
            'unknown': 'bg-secondary',
        }.get(self.status, 'bg-secondary')

    @property
    def vendor_badge_class(self):
        return 'bg-danger' if self.vendor == 'ZTE' else 'bg-primary'

    @property
    def uptime_formatted(self):
        if not self.uptime:
            return 'N/A'
        days = self.uptime // 86400
        hours = (self.uptime % 86400) // 3600
        minutes = (self.uptime % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

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
