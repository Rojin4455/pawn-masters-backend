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
    ghl_initial_refresh_token = models.TextField(default="AMf-vBxpJgKf_gXOz5hcsecLl1iBjbuQRVl9Em-Jj-OrhHkxBeIffiomwxTfR8oJxaJa7rDzuEyUGa1RRMHlPGsasVdXePuU5W3FqQFxbAT5YXBa6MN8phBnwBFXbjJ9VlsyVyHOe7Zx32bHp1CLAnsArn2Rln5ZZk4CtE5o8TkjELP2XeyXo2EyQ_ns-7K5H68mKGVW9Uzs5FuRQGcYApBnXSYR_0T4dNA7CgSlk6dXfoIqzs9uCmzO0nMCgRh-B4VVXRCr3BAX1Gf1edVWKXBslciHN1fhQ3zfkB4E7ax-wu7Plc_TsOCNeppSYVKhEeA-d_tLWecsZinMHvZlpHz2enzwk1sK2P9C9GBTJ_4KQgVqr-wV2-TZbG5hxiKHAsija1AYvJfVYZmvQK1cz0MHUZ7pb2POfjPHSfRlPP4-pFXASj3I-2OgGOZ9vUSoBtLRD8B_na-cN2WbwfuLT4XlKeD0tyZn4cLl1HLv5FP0SMCR_XpR3DWWmq1XZWvUTHZKj8tiTzqfo9QVJKBf6AQQrqxGgz1QWBDn4NizRj60qr9xSdLeRwBlNVw1ZnH8TUjhMfiIuyIcud0wlCRCHebHtSW2nx_N0g") # The static token for step 1

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
    

    class Meta:
        indexes = [
            models.Index(fields=['location_id', 'is_approved']),
            models.Index(fields=['company_id', 'is_approved']),
            models.Index(fields=['category_id', 'is_approved']),
        ]

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
    



from django.db import models
from django.utils import timezone

class LocationSyncLog(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('fetching_contacts', 'Fetching Contacts'),
        ('fetching_conversations', 'Fetching Conversations'),
        ('fetching_calls', 'Fetching Calls'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    location = models.ForeignKey(
        'GHLAuthCredentials', 
        on_delete=models.CASCADE, 
        related_name='sync_logs'
    )
    status = models.CharField(
        max_length=50, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-started_at']
        
    def __str__(self):
        return f"{self.location.location_name} - {self.status} - {self.started_at}"
    
    @property
    def duration(self):
        if self.finished_at and self.started_at:
            return self.finished_at - self.started_at
        return None


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


    class Meta:
        # db_table = "call_record"
        ordering = ['-date_added']
        indexes = [
            models.Index(fields=['date_added', 'direction']),
            models.Index(fields=['location_id', 'date_added']),  # Use direct field, not FK lookup
            models.Index(fields=['ghl_credential', 'date_added']),
            models.Index(fields=['direction']),
            models.Index(fields=['location_id']),
        ]

    def __str__(self):
        return f"Call {self.id} for {self.ghl_credential.location_name}"