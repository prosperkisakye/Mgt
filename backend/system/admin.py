
from django.contrib import admin
from .models import Institution, System, SystemInstitution, SystemHealth

@admin.register(System)
class SystemAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'description')
    search_fields = ('name', 'code')
    list_filter = ('created_at', 'updated_at')  

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_email', 'contact_phone')
    search_fields = ('name', 'contact_email', 'contact_phone')
    list_filter = ('created_at', 'updated_at')
    filter_horizontal = ('systems',)  

class SystemInstitutionInline(admin.TabularInline):
    model = SystemInstitution
    extra = 1

@admin.register(SystemInstitution)
class SystemInstitutionAdmin(admin.ModelAdmin):
    list_display = ('institution', 'system', 'type', 'external_id')
    search_fields = ('institution__name', 'system__name', 'external_id')
    list_filter = ('type', 'created_at', 'updated_at')
    autocomplete_fields = ('institution', 'system')

@admin.register(SystemHealth)
class SystemHealthAdmin(admin.ModelAdmin):
    list_display = ('system', 'status', 'last_checked', 'response_time')
    search_fields = ('system__institution__name', 'system__system__name')
    list_filter = ('status', 'last_checked')
