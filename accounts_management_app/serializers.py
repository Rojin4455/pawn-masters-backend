from rest_framework import serializers
from core.models import GHLAuthCredentials,SMSDefaultConfiguration
from rest_framework import serializers
from decimal import Decimal
from rest_framework import serializers
from category_app.serializers import CategoryCreateUpdateSerializer
from category_app.models import Category
from rest_framework import serializers
from django.db.models import Sum, F
from decimal import Decimal
from accounts_management_app.models import GHLWalletBalance


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
            "sms_inbound_usage": round(float(obj["sms_inbound_usage"]), 3),
            "sms_outbound_usage": round(float(obj["sms_outbound_usage"]), 3),
            "sms_inbound_rate": round(float(obj["sms_inbound_rate"]), 7),
            "sms_outbound_rate": round(float(obj["sms_outbound_rate"]), 7),
            "total_sms_usage": round(float(obj["total_sms_usage"]), 3)
        }

    def get_call_data(self, obj):
        return {
            "total_inbound_calls": obj["total_inbound_calls"],
            "total_outbound_calls": obj["total_outbound_calls"],
            "total_inbound_call_duration": obj["total_inbound_call_duration"],
            "total_outbound_call_duration": obj["total_outbound_call_duration"],
            "total_inbound_call_minutes": round(float(obj["inbound_call_minutes"]), 2),
            "total_outbound_call_minutes": round(float(obj["outbound_call_minutes"]), 2),
            "call_inbound_usage": round(float(obj["call_inbound_usage"]), 3),
            "call_outbound_usage": round(float(obj["call_outbound_usage"]), 3),
            "call_inbound_rate": round(float(obj["call_inbound_rate"]), 7),
            "call_outbound_rate": round(float(obj["call_outbound_rate"]), 7),
            "total_call_usage": round(float(obj["total_call_usage"]), 3)
        }

    def get_combined_totals(self, obj):
        location_id = obj.get("location_id")
        wallet_balance = Decimal('0.00') # Initialize as Decimal

        if location_id:
            try:
                # Fetch the wallet balance for this specific location
                # We use .get() on the related_name 'wallet_balance'
                wallet = GHLAuthCredentials.objects.get(location_id=location_id).wallet_balance
                if wallet.current_balance is not None:
                    wallet_balance = wallet.current_balance
            except GHLAuthCredentials.DoesNotExist:
                # Handle cases where the credential might not exist
                pass
            except GHLWalletBalance.DoesNotExist:
                # Handle cases where the wallet balance might not exist for the credential
                pass
            except Exception as e:
                # Log other potential errors
                print(f"Error fetching wallet for location {location_id}: {e}")

        return {
            "total_inbound_usage": round(float(obj["total_inbound_usage"]), 3),
            "total_outbound_usage": round(float(obj["total_outbound_usage"]), 3),
            "total_usage": round(float(obj["total_usage"]), 3),
            "wallet_balance": round(float(wallet_balance), 2) # Round wallet balance for display
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
            "sms_inbound_usage": round(float(obj["sms_inbound_usage"]), 3),
            "sms_outbound_usage": round(float(obj["sms_outbound_usage"]), 3)
        }

    def get_call_data(self, obj):
        return {
            "total_inbound_calls": obj["total_inbound_calls"],
            "total_outbound_calls": obj["total_outbound_calls"],
            "total_inbound_call_duration": obj["total_inbound_call_duration"],
            "total_outbound_call_duration": obj["total_outbound_call_duration"],
            "total_inbound_call_minutes": round(float(obj["total_inbound_call_minutes"]), 2),
            "total_outbound_call_minutes": round(float(obj["total_outbound_call_minutes"]), 2),
            "call_inbound_usage": round(float(obj["call_inbound_usage"]), 3),
            "call_outbound_usage": round(float(obj["call_outbound_usage"]), 3)
        }

    def get_combined_totals(self, obj):
        company_id = obj.get("company_id")
        total_wallet_balance = Decimal('0.00') # Initialize as Decimal

        if company_id:
            try:
                # Find all GHLAuthCredentials for this company_id
                # (Assuming GHLAuthCredentials has a 'company_id' field)
                # Then, related_name 'wallet_balance' from GHLAuthCredentials to GHLWalletBalance
                # Filter only by approved locations, if that's a requirement
                wallet_balances = GHLWalletBalance.objects.filter(
                    ghl_credential__company_id=company_id,
                    ghl_credential__is_approved=True # Filter for approved credentials if needed
                ).aggregate(total_balance=Sum('current_balance')) # Sum up current_balance

                if wallet_balances and wallet_balances['total_balance'] is not None:
                    total_wallet_balance = wallet_balances['total_balance']

            except Exception as e:
                print(f"Error fetching total wallet balance for company {company_id}: {e}")

        return {
            "total_inbound_usage": round(float(obj["total_inbound_usage"]), 3),
            "total_outbound_usage": round(float(obj["total_outbound_usage"]), 3),
            "total_usage": round(float(obj["total_usage"]), 3),
            "locations_count": obj["locations_count"],
            "total_wallet_balance": round(float(total_wallet_balance), 2) # Round for display
        }



class BarGraphAnalyticsRequestSerializer(serializers.Serializer):
    date_range = serializers.DictField(
        child=serializers.DateField(),
        required=True,
        help_text="Date range with 'start' and 'end' keys"
    )
    location_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="List of location IDs to filter by"
    )
    graph_type = serializers.ChoiceField(
        choices=['daily', 'weekly', 'monthly'],
        default='daily',
        help_text="Type of time period grouping"
    )
    data_type = serializers.ChoiceField(
        choices=['sms', 'call', 'both'],
        default='both',
        help_text="Type of data to include"
    )
    
    def validate_date_range(self, value):
        """Validate date range"""
        if 'start' not in value or 'end' not in value:
            raise serializers.ValidationError("Date range must contain 'start' and 'end' keys")
        
        if value['start'] > value['end']:
            raise serializers.ValidationError("Start date must be before or equal to end date")
        
        return value