from django.db import models
from category_app.models import Category
from decimal import Decimal
from django.core.exceptions import ValidationError





class GHLAuthCredentials(models.Model):
    user_id = models.CharField(max_length=255, null=True, blank=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_in = models.IntegerField()
    scope = models.TextField(null=True, blank=True)
    user_type = models.CharField(max_length=50, null=True, blank=True)
    company_id = models.CharField(max_length=255, null=True, blank=True)
    location_id = models.CharField(max_length=255, null=True, blank=True)
    location_name = models.CharField(max_length=255, null=True, blank=True)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    timezone = models.CharField(max_length=100, null=True, blank=True, default="")
    is_approved = models.BooleanField(default=False)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='locations')
    inbound_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Rate in USD, e.g., 0.10 for 10 cents", null=True, blank=True)    
    outbound_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Rate in USD, e.g., 0.10 for 10 cents", null=True, blank=True)
    currency = models.CharField(max_length=255, null=True, blank=True)
    is_contact_pulled = models.BooleanField(null=True, blank=True, default=False)
    is_conversation_pulled = models.BooleanField(null=True, blank=True, default=False)
    segment_length = models.IntegerField(default=160, null=True, blank=True)


    def save(self, *args, **kwargs):
        """Auto-populate rates and currency from default config if not provided"""
        if not self.inbound_rate or not self.outbound_rate or not self.currency:
            default_config = SMSDefaultConfiguration.get_instance()
            
            if not self.inbound_rate:
                self.inbound_rate = default_config.default_inbound_rate
            if not self.outbound_rate:
                self.outbound_rate = default_config.default_outbound_rate
            if not self.currency:
                self.currency = default_config.default_currency
                
        super().save(*args, **kwargs)
    

    def __str__(self):
        return f"{self.location_name} - {self.location_id}"


class SMSDefaultConfiguration(models.Model):
    """
    Singleton model to store default SMS configuration for the entire application
    """
    default_inbound_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.10'),
        help_text="Default inbound rate in USD, e.g., 0.10 for 10 cents"
    )
    default_outbound_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.10'),
        help_text="Default outbound rate in USD, e.g., 0.10 for 10 cents"
    )
    default_currency = models.CharField(
        max_length=10, 
        default='USD',
        help_text="Default currency code, e.g., USD, EUR, GBP"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "SMS Default Configuration"
        verbose_name_plural = "SMS Default Configuration"
    
    def save(self, *args, **kwargs):
        """Ensure only one instance exists (singleton pattern)"""
        if not self.pk and SMSDefaultConfiguration.objects.exists():
            raise ValidationError('Only one SMS default configuration is allowed.')
        return super().save(*args, **kwargs)
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        instance, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'default_inbound_rate': Decimal('0.10'),
                'default_outbound_rate': Decimal('0.10'),
                'default_currency': 'USD'
            }
        )
        return instance
    
    def __str__(self):
        return f"SMS Config - Inbound: {self.default_inbound_rate} {self.default_currency}, Outbound: {self.default_outbound_rate} {self.default_currency}"