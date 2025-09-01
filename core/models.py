from django.db import models
from category_app.models import Category
from decimal import Decimal
from django.core.exceptions import ValidationError
# from accounts_management_app.models import GHLConversation





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
    inbound_rate = models.DecimalField(max_digits=10, decimal_places=7, help_text="Rate in USD, e.g., 0.10 for 10 cents", null=True, blank=True)    
    outbound_rate = models.DecimalField(max_digits=10, decimal_places=7, help_text="Rate in USD, e.g., 0.10 for 10 cents", null=True, blank=True)
    inbound_call_rate = models.DecimalField(max_digits=10, decimal_places=7, help_text="Rate in USD, e.g., 0.10 for 10 cents", null=True, blank=True)    
    outbound_call_rate = models.DecimalField(max_digits=10, decimal_places=7, help_text="Rate in USD, e.g., 0.10 for 10 cents", null=True, blank=True)
    call_price_ratio = models.DecimalField(max_digits=10, decimal_places=7, help_text="Rate in USD, e.g., 0.10 for 10 cents", null=True, blank=True)
    currency = models.CharField(max_length=255, null=True, blank=True)
    is_contact_pulled = models.BooleanField(null=True, blank=True, default=False)
    is_conversation_pulled = models.BooleanField(null=True, blank=True, default=False)
    is_calls_pulled = models.BooleanField(null=True, blank=True, default=False)
    segment_length = models.IntegerField(default=160, null=True, blank=True)
    ghl_initial_refresh_token = models.TextField(null=True, blank=True) # The static token for step 1



    def save(self, *args, **kwargs):
        """Auto-populate rates and currency from default config if not provided"""
        if not self.inbound_rate or not self.outbound_rate or not self.currency or not self.outbound_call_rate or not self.inbound_call_rate:
            default_config = SMSDefaultConfiguration.get_instance()
            
            if not self.inbound_rate:
                self.inbound_rate = default_config.default_inbound_rate
            if not self.outbound_rate:
                self.outbound_rate = default_config.default_outbound_rate
            if not self.currency:
                self.currency = default_config.default_currency
            if not self.outbound_call_rate:
                self.outbound_call_rate = default_config.default_call_outbound_rate
            if not self.inbound_call_rate:
                self.inbound_call_rate = default_config.default_call_inbound_rate
                
        super().save(*args, **kwargs)
    

    def __str__(self):
        return f"{self.location_name} - {self.location_id}"


class SMSDefaultConfiguration(models.Model):
    """
    Singleton model to store default SMS configuration for the entire application
    """
    default_inbound_rate = models.DecimalField(
        max_digits=10, decimal_places=7, 
        default=Decimal('0.10'),
        help_text="Default inbound rate in USD, e.g., 0.10 for 10 cents"
    )
    default_outbound_rate = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
        default=Decimal('0.10'),
        help_text="Default outbound rate in USD, e.g., 0.10 for 10 cents"
    )
    default_call_inbound_rate = models.DecimalField(
        max_digits=10, decimal_places=7, 
        default=Decimal('0.10'),
        help_text="Default inbound rate in USD, e.g., 0.10 for 10 cents"
    )
    default_call_outbound_rate = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
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
    



class LocationSyncLog(models.Model):
    location = models.ForeignKey(GHLAuthCredentials, on_delete=models.CASCADE, related_name="sync_logs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        default="pending",
    )


class FirebaseToken(models.Model):
    ghl_credential = models.OneToOneField(GHLAuthCredentials, on_delete=models.CASCADE, related_name='firebase_token')
    access_token = models.TextField()
    expires_in = models.IntegerField()
    token_type = models.CharField(max_length=50)
    refresh_token = models.TextField()
    id_token = models.TextField()
    user_id = models.CharField(max_length=100)
    project_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Firebase Token for {self.ghl_credential.location_name}"


class LeadConnectorAuth(models.Model):
    ghl_credential = models.OneToOneField(GHLAuthCredentials, on_delete=models.CASCADE, related_name='leadconnector_auth')
    token = models.TextField()
    trace_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"LeadConnector Auth for {self.ghl_credential.location_name}"


class IdentityToolkitAuth(models.Model):
    ghl_credential = models.OneToOneField(GHLAuthCredentials, on_delete=models.CASCADE, related_name='identitytoolkit_auth')
    kind = models.CharField(max_length=100)
    id_token = models.TextField()
    refresh_token = models.TextField()
    expires_in = models.IntegerField()
    is_new_user = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"IdentityToolkit Auth for {self.ghl_credential.location_name}"


class CallReport(models.Model):
    # Link CallReport to GHLAuthCredentials
    ghl_credential = models.ForeignKey(GHLAuthCredentials, on_delete=models.CASCADE, related_name='call_reports', null=True, blank=True)
    id = models.CharField(max_length=255, primary_key=True) # GHL provides 'id' for calls, use it as primary key
    conversation = models.ForeignKey('accounts_management_app.GHLConversation', on_delete=models.CASCADE, related_name='call_report', null=True, blank=True)
    account_sid = models.CharField(max_length=255, null=True, blank=True)
    assigned_to = models.CharField(max_length=255, null=True, blank=True)
    call_sid = models.CharField(max_length=255, null=True, blank=True)
    call_status = models.CharField(max_length=50, null=True, blank=True)
    contact_id = models.CharField(max_length=255, null=True, blank=True)
    date_added = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(null=True, blank=True)
    deleted = models.BooleanField(default=False)
    direction = models.CharField(max_length=50, null=True, blank=True)
    from_number = models.CharField(max_length=20, null=True, blank=True)
    location_id = models.CharField(max_length=255, null=True, blank=True) # Redundant if linked by FK, but good for data integrity
    message_id = models.CharField(max_length=255, null=True, blank=True)
    to_number = models.CharField(max_length=20, null=True, blank=True)
    user_id = models.CharField(max_length=255, null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(default=0, null=True, blank=True)
    first_time = models.BooleanField(default=False, null=True, blank=True)
    recording_url = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True) # Add created_at for tracking

    # called = models.CharField(max_length=20, null=True, blank=True)
    # called_city = models.CharField(max_length=100, null=True, blank=True)
    # called_country = models.CharField(max_length=100, null=True, blank=True)
    # called_state = models.CharField(max_length=100, null=True, blank=True)
    # called_zip = models.CharField(max_length=20, null=True, blank=True)
    # caller = models.CharField(max_length=20, null=True, blank=True)
    # caller_city = models.CharField(max_length=100, null=True, blank=True)
    # caller_country = models.CharField(max_length=100, null=True, blank=True)
    # caller_state = models.CharField(max_length=100, null=True, blank=True)
    # caller_zip = models.CharField(max_length=20, null=True, blank=True)
    # from_city = models.CharField(max_length=100, null=True, blank=True)
    # from_country = models.CharField(max_length=100, null=True, blank=True)
    # from_state = models.CharField(max_length=100, null=True, blank=True)
    # from_zip = models.CharField(max_length=20, null=True, blank=True)
    # to_city = models.CharField(max_length=100, null=True, blank=True)
    # to_country = models.CharField(max_length=100, null=True, blank=True)
    # to_state = models.CharField(max_length=100, null=True, blank=True)
    # to_zip = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"Call {self.id} for {self.ghl_credential.location_name}"