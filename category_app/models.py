from django.db import models
from django.utils import timezone

class Category(models.Model):
    category_name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    color = models.CharField(max_length=7, help_text="Hex color code, e.g., #FF0000")  # For hex colors like #FF0000
    is_active = models.BooleanField(default=True)
    added_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.category_name
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['-added_date']