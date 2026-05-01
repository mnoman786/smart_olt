from django.contrib import admin
from .models import AlertRule, AlertNotification


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'threshold', 'enabled', 'notify_email', 'notify_sms']
    list_filter = ['type', 'enabled']


@admin.register(AlertNotification)
class AlertNotificationAdmin(admin.ModelAdmin):
    list_display = ['rule', 'channel', 'recipient', 'sent_at', 'delivered']
    list_filter = ['channel', 'delivered']
