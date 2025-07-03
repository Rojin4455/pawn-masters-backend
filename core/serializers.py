from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model
    """
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'date_joined')
        read_only_fields = ('id', 'date_joined')


class RegisterSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration
    """
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm', 'first_name', 'last_name')
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Password fields didn't match.")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user
    





from rest_framework import serializers
from .models import FirebaseToken, LeadConnectorAuth, IdentityToolkitAuth, GHLAuthCredentials, CallReport

class GHLAuthCredentialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GHLAuthCredentials
        fields = '__all__'


class FirebaseTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirebaseToken
        fields = '__all__'
        read_only_fields = ['ghl_credential'] # ghl_credential will be set programmatically


class LeadConnectorAuthSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadConnectorAuth
        fields = '__all__'
        read_only_fields = ['ghl_credential']


class IdentityToolkitAuthSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentityToolkitAuth
        fields = '__all__'
        read_only_fields = ['ghl_credential']

class CallReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallReport
        fields = '__all__'
        read_only_fields = ['ghl_credential']
