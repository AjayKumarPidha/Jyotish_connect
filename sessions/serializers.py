from rest_framework import serializers
from .models import Session, BillingTick


class StartSessionSerializer(serializers.Serializer):
    astrologer_id = serializers.UUIDField()
    session_type  = serializers.ChoiceField(choices=Session.TYPE_CHOICES)


class BillingTickSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BillingTick
        fields = ['id', 'amount_deducted', 'is_free_tick', 'created_at']


class SessionSerializer(serializers.ModelSerializer):
    client_phone      = serializers.CharField(source='client.phone', read_only=True)
    astrologer_name   = serializers.CharField(source='astrologer.display_name', read_only=True)

    class Meta:
        model  = Session
        fields = [
            'id', 'client_phone', 'astrologer_name',
            'session_type', 'status', 'rate_per_min',
            'duration_minutes', 'total_amount',
            'platform_commission', 'astrologer_earnings',
            'is_free_session', 'agora_channel',
            'started_at', 'ended_at', 'created_at',
        ]
