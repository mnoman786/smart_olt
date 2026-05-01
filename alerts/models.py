from django.db import models


class AlertRule(models.Model):
    TYPE_CHOICES = [
        ('signal_low', 'Signal Too Low'),
        ('signal_high', 'Signal Too High'),
        ('ont_offline', 'ONT Offline'),
        ('olt_offline', 'OLT Offline'),
        ('high_traffic', 'High Traffic'),
        ('temperature', 'High Temperature'),
    ]
    OPERATOR_CHOICES = [
        ('lt', 'Less than (<)'),
        ('gt', 'Greater than (>)'),
        ('eq', 'Equal to (=)'),
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    threshold = models.FloatField(null=True, blank=True)
    operator = models.CharField(max_length=5, choices=OPERATOR_CHOICES, default='lt')
    enabled = models.BooleanField(default=True)
    notify_email = models.BooleanField(default=True)
    notify_sms = models.BooleanField(default=False)
    email_recipients = models.TextField(blank=True, help_text='Comma-separated email addresses')
    sms_recipients = models.TextField(blank=True, help_text='Comma-separated phone numbers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def type_icon(self):
        return {
            'signal_low': 'fa-signal',
            'signal_high': 'fa-signal',
            'ont_offline': 'fa-plug-circle-xmark',
            'olt_offline': 'fa-server',
            'high_traffic': 'fa-gauge-high',
            'temperature': 'fa-temperature-high',
        }.get(self.type, 'fa-bell')

    class Meta:
        ordering = ['name']


class AlertNotification(models.Model):
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
    ]

    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='notifications')
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    recipient = models.CharField(max_length=200)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    delivered = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.rule.name} → {self.recipient} ({self.channel})"

    class Meta:
        ordering = ['-sent_at']
