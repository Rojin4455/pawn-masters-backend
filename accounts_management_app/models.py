from django.db import models
from django.core.exceptions import ValidationError
from core.models import GHLAuthCredentials

class Contact(models.Model):
    contact_id = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    dnd = models.BooleanField(default=False)
    country = models.CharField(max_length=50, blank=True, null=True)
    date_added = models.DateTimeField(blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    custom_fields = models.JSONField(default=list, blank=True)
    location_id = models.CharField(max_length=100)
    timestamp = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    


class GHLConversation(models.Model):
    conversation_id = models.CharField(max_length=100, unique=True)
    location = models.ForeignKey(
        GHLAuthCredentials,
        on_delete=models.CASCADE,
        related_name="conversations"
    )
    contact = models.ForeignKey(Contact, to_field="contact_id", db_column="contact_id", on_delete=models.SET_NULL, null=True, blank=True)
    last_message_body = models.TextField(null=True, blank=True)
    last_message_type = models.CharField(max_length=50, null=True, blank=True)
    last_message_direction = models.CharField(max_length=50, null=True, blank=True)
    last_outbound_action = models.CharField(max_length=50, null=True, blank=True)
    unread_count = models.IntegerField(null=True, blank=True)
    date_added = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(null=True, blank=True)
    last_manual_message_date = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)


    class Meta:
        db_table = "ghl_conversation"

    def __str__(self):
        return f"{self.conversation_id}"
    

    


class TextMessage(models.Model):
    
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('read', 'Read'),
    ]
    
    message_id = models.CharField(max_length=255, unique=True, db_index=True)
    conversation = models.ForeignKey('GHLConversation', on_delete=models.CASCADE, related_name='messages')
    
    # Message content
    body = models.TextField(blank=True, null=True)
    content_type = models.CharField(max_length=100, default='text/plain')
    message_type = models.CharField(max_length=50)
    
    # New fields for SMS calculation
    body_length = models.IntegerField(default=0, help_text="Length of the message body")
    segments = models.IntegerField(default=1, help_text="Number of SMS segments used")
    
    # Message metadata
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True, null=True)
    type = models.IntegerField(help_text="Message type ID from API")
    source = models.CharField(max_length=100, blank=True, null=True)
    
    # User info
    user_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Attachments (stored as JSON)
    attachments = models.JSONField(default=list, blank=True)
    
    # Timestamps
    date_added = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "text_message"
        ordering = ['-date_added']
        indexes = [
            models.Index(fields=['conversation', 'date_added']),
            models.Index(fields=['segments', 'date_added']),  # Added for segment-based queries
        ]
    
    
    def __str__(self):
        return f"Message {self.message_id} - {self.message_type} ({self.direction}) - {self.segments} segments"
    



class CallRecord(models.Model):
    
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]
    

    
    # Primary identifiers
    message_id = models.CharField(max_length=255, unique=True, db_index=True)
    conversation = models.ForeignKey('GHLConversation', on_delete=models.CASCADE, related_name='call_records')
    alt_id = models.CharField(max_length=255, blank=True, null=True, help_text="Alternative ID from GHL")
    
    # Call specific fields
    message_type = models.CharField(max_length=50, default='TYPE_CALL')
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    status = models.CharField(max_length=20, blank=True, null=True)
    type = models.IntegerField(help_text="Message type ID from API")
    
    # Call duration and metadata
    duration = models.IntegerField(default=0, help_text="Call duration in seconds", null=True, blank=True)
    duration_formatted = models.CharField(max_length=20, blank=True, null=True, help_text="Formatted duration (MM:SS)")
    
    # Call metadata (stored as JSON for flexibility)
    call_meta = models.JSONField(default=dict, blank=True, help_text="Additional call metadata from API")
    
    # Location and contact info
    location_id = models.CharField(max_length=255, blank=True, null=True)
    contact_id = models.CharField(max_length=255, blank=True, null=True)
    
    # User info
    user_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Timestamps
    date_added = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "call_record"
        ordering = ['-date_added']
        indexes = [
            models.Index(fields=['conversation', 'date_added']),
            models.Index(fields=['duration', 'date_added']),
            models.Index(fields=['status', 'date_added']),
            models.Index(fields=['direction', 'date_added']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-format duration as MM:SS
        if self.duration:
            minutes = self.duration // 60
            seconds = self.duration % 60
            self.duration_formatted = f"{minutes:02d}:{seconds:02d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Call {self.message_id} - {self.direction} - {self.duration_formatted or '00:00'} - {self.status}"



class WebhookLog(models.Model):
    received_at = models.DateTimeField(auto_now_add=True)
    data = models.TextField(null=True, blank=True)
    webhook_id = models.CharField(null=True, blank=True, max_length=200)

    def __str__(self):
        return f"{self.webhook_id} : {self.received_at}"
    





class GHLWalletBalance(models.Model):

    ghl_credential = models.OneToOneField(
        'core.GHLAuthCredentials', # Replace 'core' with your actual app name if different
        on_delete=models.CASCADE,
        primary_key=True, # Makes this field the primary key, simplifying lookup
        related_name='wallet_balance' # Allows you to access balance from credential: credential.wallet_balance
    )
    current_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True) # Tracks when it was last updated

    def __str__(self):
        return f"Wallet for {self.ghl_credential.location_name} - Balance: {self.current_balance}"

    class Meta:
        verbose_name = "GHL Wallet Balance"
        verbose_name_plural = "GHL Wallet Balances"