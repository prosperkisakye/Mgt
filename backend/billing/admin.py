from django.contrib import admin
from .models import BillingPackage, CustomPackage, SystemInsitutionBillingPackage

@admin.register(BillingPackage)
class BillingPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'system', 'type', 'price')
    search_fields = ('name', 'system__name')
    list_filter = ('type', 'system', 'created_at', 'updated_at')

@admin.register(CustomPackage)
class CustomPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'price')
    search_fields = ('name',)
    list_filter = ('type', 'created_at', 'updated_at')

@admin.register(SystemInsitutionBillingPackage)
class SystemInsitutionBillingPackageAdmin(admin.ModelAdmin):
    list_display = ('system', 'package_or_custom', 'frequency')
    search_fields = ('system__institution__name', 'system__system__name', 'package__name', 'custom_package__name')
    list_filter = ('frequency', 'created_at', 'updated_at')
    autocomplete_fields = ('system', 'package', 'custom_package')

    def package_or_custom(self, obj):
        return obj.package or obj.custom_package
    package_or_custom.short_description = "Package"
