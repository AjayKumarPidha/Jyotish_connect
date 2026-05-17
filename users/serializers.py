from rest_framework import serializers
from .models import User


class PhoneCheckSerializer(serializers.Serializer):
    """Screen 1 Step 1 — just a phone number."""
    phone = serializers.CharField(max_length=15)

    def validate_phone(self, value):
        value = value.strip().replace(' ', '')
        if not value.startswith('+'):
            # Accept 10-digit Indian numbers and auto-prefix
            if len(value) == 10 and value.isdigit():
                value = '+91' + value
            else:
                raise serializers.ValidationError(
                    'Enter a valid phone number (e.g. +919999999999 or 9999999999).'
                )
        return value


class FirebaseVerifySerializer(serializers.Serializer):
    """Screen 1 Step 2 — phone + Firebase ID token after OTP."""
    phone          = serializers.CharField(max_length=15)
    firebase_token = serializers.CharField()   # Firebase idToken from client SDK

    def validate_phone(self, value):
        value = value.strip().replace(' ', '')
        if not value.startswith('+'):
            if len(value) == 10 and value.isdigit():
                value = '+91' + value
            else:
                raise serializers.ValidationError('Enter a valid phone number.')
        return value


class CompleteProfileSerializer(serializers.Serializer):
    """Screen 2 — profile completion after OTP verified."""
    full_name    = serializers.CharField(max_length=150)
    gender       = serializers.ChoiceField(
        choices=['male', 'female', 'other'], required=False
    )
    date_of_birth = serializers.DateField(required=False)
    role         = serializers.ChoiceField(
        choices=[User.ROLE_CLIENT, User.ROLE_ASTROLOGER],
        default=User.ROLE_CLIENT,
        required=False,
    )

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Full name must be at least 2 characters.')
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    """Read/update user profile."""
    class Meta:
        model  = User
        fields = [
            'phone', 'full_name', 'gender', 'date_of_birth',
            'role', 'has_used_free_session', 'created_at',
        ]
        read_only_fields = ['phone', 'role', 'has_used_free_session', 'created_at']