from django.contrib import admin
from .models import OLT, PONPort


@admin.register(OLT)
class OLTAdmin(admin.ModelAdmin):
    list_display = ['name', 'vendor', 'model', 'ip_address', 'status', 'location']
    list_filter = ['vendor', 'status', 'is_active']
    search_fields = ['name', 'ip_address', 'location']


@admin.register(PONPort)
class PONPortAdmin(admin.ModelAdmin):
    list_display = ['olt', 'board', 'port', 'technology', 'status', 'ont_count']
    list_filter = ['technology', 'status']
    search_fields = ['olt__name']
