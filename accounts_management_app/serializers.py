from rest_framework import serializers
from core.models import GHLAuthCredentials,SMSDefaultConfiguration
from rest_framework import serializers
from decimal import Decimal
from rest_framework import serializers
from category_app.serializers import CategoryCreateUpdateSerializer
from category_app.models import Category


class GHLAuthCredentialsSerializer(serializers.ModelSerializer):
    category = CategoryCreateUpdateSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True,
        required=False,  # <-- Make it optional
        allow_null=True 
    )

    class Meta:
        model = GHLAuthCredentials
        fields = [
            'id',
            'company_id', 'location_id', 'location_name', 'company_name', 'is_approved',
            'category', 'inbound_rate', 'outbound_rate', 'category_id','outbound_call_rate','inbound_call_rate','call_price_ratio'
        ]


class CompanyNameSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = GHLAuthCredentials
        fields = ['id', 'company_name', 'company_id']


class AccountViewSerializer(serializers.Serializer):
    """Serializer for Account View (per location) data"""
    company_name = serializers.CharField()
    location_name = serializers.CharField()
    location_id = serializers.CharField()
    total_inbound_segments = serializers.IntegerField()
    total_outbound_segments = serializers.IntegerField()
    total_inbound_messages = serializers.IntegerField()
    total_outbound_messages = serializers.IntegerField()
    total_inbound_usage = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_outbound_usage = serializers.DecimalField(max_digits=10, decimal_places=2)
    inbound_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    outbound_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_usage = serializers.DecimalField(max_digits=10, decimal_places=2)


class CompanyViewSerializer(serializers.Serializer):
    """Serializer for Company View (aggregated) data"""
    company_name = serializers.CharField()
    company_id = serializers.CharField()
    total_inbound_segments = serializers.IntegerField()
    total_outbound_segments = serializers.IntegerField()
    total_inbound_messages = serializers.IntegerField()
    total_outbound_messages = serializers.IntegerField()
    total_inbound_usage = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_outbound_usage = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_usage = serializers.DecimalField(max_digits=10, decimal_places=2)
    locations_count = serializers.IntegerField()


class AnalyticsRequestSerializer(serializers.Serializer):
    """Serializer for request payload validation"""
    view_type = serializers.ChoiceField(
        choices=['account', 'company'], 
        default='account',
        help_text="Type of view: 'account' for per-location, 'company' for aggregated"
    )
    date_range = serializers.DictField(
        child=serializers.DateTimeField(),
        required=False,
        help_text="Date range filter with 'start' and 'end' keys"
    )
    category = serializers.IntegerField(required=False, help_text="Category ID filter")
    company_id = serializers.CharField(required=False, help_text="Company ID filter")

    def validate_date_range(self, value):
        """Validate date_range has both start and end dates"""
        if value and ('start' not in value or 'end' not in value):
            raise serializers.ValidationError(
                "date_range must contain both 'start' and 'end' keys"
            )
        return value
    






class SMSDefaultConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for SMS Default Configuration"""
    
    class Meta:
        model = SMSDefaultConfiguration
        fields = [
            'default_inbound_rate', 
            'default_outbound_rate', 
            'default_call_inbound_rate',
            'default_call_outbound_rate',
            'default_currency',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_default_inbound_rate(self, value):
        """Validate inbound rate is positive"""
        if value <= 0:
            raise serializers.ValidationError("Inbound rate must be greater than 0")
        return value

    def validate_default_outbound_rate(self, value):
        """Validate outbound rate is positive"""
        if value <= 0:
            raise serializers.ValidationError("Outbound rate must be greater than 0")
        return value
    

    def validate_default_call_inbound_rate(self, value):
        """Validate inbound rate is positive"""
        if value <= 0:
            raise serializers.ValidationError("Inbound rate must be greater than 0")
        return value

    def validate_default_call_outbound_rate(self, value):
        """Validate outbound rate is positive"""
        if value <= 0:
            raise serializers.ValidationError("Outbound rate must be greater than 0")
        return value

    def validate_default_currency(self, value):
        """Validate currency code format"""
        if not value or len(value) < 2:
            raise serializers.ValidationError("Currency code must be at least 2 characters")
        return value.upper()
    

class GHLCredentialsUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating GHL credentials with bulk rate updates"""
    
    class Meta:
        model = GHLAuthCredentials
        fields = ['inbound_rate', 'outbound_rate', 'currency']



class AccountViewWithCallsSerializer(serializers.Serializer):
    company_name = serializers.CharField()
    location_name = serializers.CharField()
    location_id = serializers.CharField()

    sms_data = serializers.SerializerMethodField()
    call_data = serializers.SerializerMethodField()
    combined_totals = serializers.SerializerMethodField()

    def get_sms_data(self, obj):
        return {
            "total_inbound_segments": obj["total_inbound_segments"],
            "total_outbound_segments": obj["total_outbound_segments"],
            "total_inbound_messages": obj["total_inbound_messages"],
            "total_outbound_messages": obj["total_outbound_messages"],
            "sms_inbound_usage": obj["sms_inbound_usage"],
            "sms_outbound_usage": obj["sms_outbound_usage"],
            "sms_inbound_rate": obj["sms_inbound_rate"],
            "sms_outbound_rate": obj["sms_outbound_rate"],
            # "total_inbound_sms_usage": obj["total_inbound_usage"],
            # "total_outbound_sms_usage": obj["total_outbound_usage"],
            "total_sms_usage": obj["total_usage"]
        }

    def get_call_data(self, obj):
        return {
            "total_inbound_calls": obj["total_inbound_calls"],
            "total_outbound_calls": obj["total_outbound_calls"],
            "total_inbound_call_duration": obj["total_inbound_call_duration"],
            "total_outbound_call_duration": obj["total_outbound_call_duration"],
            "inbound_call_minutes": obj["inbound_call_minutes"],
            "outbound_call_minutes": obj["outbound_call_minutes"],
            "call_inbound_usage": obj["call_inbound_usage"],
            "call_outbound_usage": obj["call_outbound_usage"],
            "call_inbound_rate": obj["call_inbound_rate"],
            "call_outbound_rate": obj["call_outbound_rate"]
        }

    def get_combined_totals(self, obj):
        return {
            "total_inbound_usage": obj["total_inbound_usage"],
            "total_outbound_usage": obj["total_outbound_usage"],
            "total_usage": obj["total_usage"]
        }



class CompanyViewWithCallsSerializer(serializers.Serializer):
    company_name = serializers.CharField()
    company_id = serializers.CharField()

    sms_data = serializers.SerializerMethodField()
    call_data = serializers.SerializerMethodField()
    combined_totals = serializers.SerializerMethodField()

    def get_sms_data(self, obj):
        return {
            "total_inbound_segments": obj["total_inbound_segments"],
            "total_outbound_segments": obj["total_outbound_segments"],
            "total_inbound_messages": obj["total_inbound_messages"],
            "total_outbound_messages": obj["total_outbound_messages"],
            "sms_inbound_usage": obj["sms_inbound_usage"],
            "sms_outbound_usage": obj["sms_outbound_usage"]
        }

    def get_call_data(self, obj):
        return {
            "total_inbound_calls": obj["total_inbound_calls"],
            "total_outbound_calls": obj["total_outbound_calls"],
            "total_inbound_call_duration": obj["total_inbound_call_duration"],
            "total_outbound_call_duration": obj["total_outbound_call_duration"],
            "total_inbound_call_minutes": obj["total_inbound_call_minutes"],
            "total_outbound_call_minutes": obj["total_outbound_call_minutes"],
            "call_inbound_usage": obj["call_inbound_usage"],
            "call_outbound_usage": obj["call_outbound_usage"]
        }

    def get_combined_totals(self, obj):
        return {
            "total_inbound_usage": obj["total_inbound_usage"],
            "total_outbound_usage": obj["total_outbound_usage"],
            "total_usage": obj["total_usage"],
            "locations_count": obj["locations_count"]
        }