from rest_framework import serializers
from .models import User


# ─── Shared phone validator ────────────────────────────────────────────────────
def normalize_phone(value: str) -> str:
    value = value.strip().replace(' ', '')
    if not value.startswith('+'):
        if len(value) == 10 and value.isdigit():
            return '+91' + value
        raise serializers.ValidationError(
            'Enter a valid phone number (e.g. +919999999999 or 9999999999).'
        )
    return value


# ─── Screen 1: Step 1 ─────────────────────────────────────────────────────────
class PhoneCheckSerializer(serializers.Serializer):
    """POST /auth/check-phone/ — check if phone exists."""
    phone = serializers.CharField(max_length=15)

    def validate_phone(self, value):
        return normalize_phone(value)


# ─── Screen 1: Step 2a ────────────────────────────────────────────────────────
class SendOTPSerializer(serializers.Serializer):
    """POST /auth/send-otp/ — trigger OTP for a phone number."""
    phone = serializers.CharField(max_length=15)

    def validate_phone(self, value):
        return normalize_phone(value)


# ─── Screen 1: Step 2b ────────────────────────────────────────────────────────
class VerifyOTPSerializer(serializers.Serializer):
    """POST /auth/verify-otp/ — submit OTP code."""
    phone    = serializers.CharField(max_length=15)
    otp_code = serializers.CharField(max_length=10)

    def validate_phone(self, value):
        return normalize_phone(value)

    def validate_otp_code(self, value):
        return value.strip()


# ─── Screen 2: Profile Completion ────────────────────────────────────────────
class CompleteProfileSerializer(serializers.Serializer):
    """POST /auth/complete-profile/ — new user fills in details."""
    temp_token          = serializers.CharField()
    full_name           = serializers.CharField(max_length=150)
    gender              = serializers.ChoiceField(
        choices=['male', 'female', 'other'], required=False
    )
    date_of_birth       = serializers.DateField(required=False)
    place_of_birth      = serializers.CharField(max_length=255, required=False, allow_blank=True)
    time_of_birth       = serializers.TimeField(
        required=False, allow_null=True,
        help_text="HH:MM format. Leave null if birth_time_unknown=true"
    )
    birth_time_unknown  = serializers.BooleanField(default=False)
    role                = serializers.ChoiceField(
        choices=[User.ROLE_CLIENT, User.ROLE_ASTROLOGER],
        default=User.ROLE_CLIENT,
        required=False,
    )

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Full name must be at least 2 characters.')
        return value

    def validate(self, data):
        # If birth_time_unknown is True, time_of_birth must be null/absent
        if data.get('birth_time_unknown') and data.get('time_of_birth'):
            raise serializers.ValidationError(
                "Cannot provide time_of_birth when birth_time_unknown is true."
            )
        return data


# ─── Profile View / Edit ──────────────────────────────────────────────────────
class UserProfileSerializer(serializers.ModelSerializer):
    """GET /auth/profile/ and PUT /auth/profile/."""
    class Meta:
        model  = User
        fields = [
            'phone', 'full_name', 'gender', 'date_of_birth',
            'place_of_birth', 'time_of_birth', 'birth_time_unknown',
            'profile_photo', 'role', 'has_used_free_session', 'created_at',
        ]
        read_only_fields = ['phone', 'role', 'has_used_free_session', 'created_at']

    def validate(self, data):
        if data.get('birth_time_unknown') and data.get('time_of_birth'):
            raise serializers.ValidationError(
                "Cannot provide time_of_birth when birth_time_unknown is true."
            )
        if data.get('birth_time_unknown'):
            data['time_of_birth'] = None
        return data
