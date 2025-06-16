from rest_framework import serializers
from .models import Category
from core.models import GHLAuthCredentials

class CategorySerializer(serializers.ModelSerializer):
    locations_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'category_name', 'description', 'color', 'is_active', 
                 'added_date', 'updated_date', 'locations_count']
        read_only_fields = ['added_date', 'updated_date']
    
    def get_locations_count(self, obj):
        return obj.locations.count()
    
    def validate_color(self, value):
        """Validate that color is a valid hex color code"""
        if not value.startswith('#') or len(value) != 7:
            raise serializers.ValidationError("Color must be a valid hex color code (e.g., #FF0000)")
        try:
            int(value[1:], 16)  # Check if it's a valid hex
        except ValueError:
            raise serializers.ValidationError("Color must be a valid hex color code (e.g., #FF0000)")
        return value

class CategoryCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['category_name', 'description', 'color', 'is_active','id']
    
    def validate_color(self, value):
        """Validate that color is a valid hex color code"""
        if not value.startswith('#') or len(value) != 7:
            raise serializers.ValidationError("Color must be a valid hex color code (e.g., #FF0000)")
        try:
            int(value[1:], 16)  # Check if it's a valid hex
        except ValueError:
            raise serializers.ValidationError("Color must be a valid hex color code (e.g., #FF0000)")
        return value
