from django.db import models

from utilities.models import SoftDeletableTimeStampedModel

class BillingPackage(SoftDeletableTimeStampedModel):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    system = models.ForeignKey('system.System', on_delete=models.CASCADE, related_name='billing_packages')
    type = models.CharField(max_length=50, choices=[('per_user', 'Per User')])

    def __str__(self):
        return self.name
    
class CustomPackage(SoftDeletableTimeStampedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    type = models.CharField(max_length=50, choices=[('per_user', 'Per User')])

    def __str__(self):
        return self.name

class SystemInsitutionBillingPackage(SoftDeletableTimeStampedModel):
    system = models.ForeignKey('system.SystemInstitution', on_delete=models.CASCADE)
    package = models.ForeignKey(BillingPackage, on_delete=models.CASCADE, null=True, blank=True)
    custom_package = models.ForeignKey(CustomPackage, on_delete=models.CASCADE, null=True, blank=True)
    frequency = models.CharField(max_length=50, choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')])

    def __str__(self):
        return f"{self.system} - {self.package or self.custom_package}"        
    
