from django.db import models
from category_app.models import Category


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
    is_contact_pulled = models.BooleanField(null=True, blank=True, default=False)
    is_conversation_pulled = models.BooleanField(null=True, blank=True, default=False)
    segment_length = models.IntegerField(default=160, null=True, blank=True)
    

    def __str__(self):
        return f"{self.location_name} - {self.location_id}"
