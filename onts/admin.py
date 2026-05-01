from django.contrib import admin
from .models import ONT, ONTProfile


@admin.register(ONTProfile)
class ONTProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'vendor', 'download_speed', 'upload_speed', 'protocol']
    list_filter = ['vendor', 'protocol']


@admin.register(ONT)
class ONTAdmin(admin.ModelAdmin):
    list_display = ['name', 'serial_number', 'olt', 'status', 'rx_power', 'ip_address']
    list_filter = ['status', 'technology', 'mode', 'olt']
    search_fields = ['name', 'serial_number', 'ip_address', 'mac_address']
    raw_id_fields = ['olt', 'pon_port', 'profile']
