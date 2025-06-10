from rest_framework import serializers
from core.models import GHLAuthCredentials

class GHLAuthCredentialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GHLAuthCredentials
        fields = [
            'id',
            'company_id', 'location_id', 'location_name', 'company_name', 'is_approved',
            'category', 'inbound_rate', 'outbound_rate'
        ]