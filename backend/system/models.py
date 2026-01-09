from django.db import models
from utilities.models import SoftDeletableTimeStampedModel

class Institution(SoftDeletableTimeStampedModel):
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    systems = models.ManyToManyField('System', related_name='institutions')
    

    def __str__(self):
        return self.name

class System(SoftDeletableTimeStampedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='system/logos/', blank=True, null=True)
    code = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
class SystemInstitution(SoftDeletableTimeStampedModel):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    system = models.ForeignKey(System, on_delete=models.CASCADE)
    type = models.CharField(max_length=50, choices=[('direct', 'Direct'), ('integration', 'Integration')])
    external_id = models.CharField(max_length=255, blank=True, null=True)
    billing_packages = models.ManyToManyField('billing.BillingPackage', through='billing.SystemInsitutionBillingPackage', related_name='system_institutions')

    def __str__(self):
        return f"{self.institution.name} - {self.system.name}"
    
class SystemHealth(SoftDeletableTimeStampedModel):
    system = models.ForeignKey(SystemInstitution, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=[('healthy', 'Healthy'), ('degraded', 'Degraded'), ('down', 'Down')])
    last_checked = models.DateTimeField(auto_now=True)
    response_time = models.FloatField(help_text="Response time in milliseconds")
    details = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.system} - {self.status}"