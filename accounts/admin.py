from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'organization']
    list_filter = []
    search_fields = ['user__username', 'user__email', 'organization']
