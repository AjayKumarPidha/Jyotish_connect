from rest_framework import serializers
from .models import Wallet, Transaction, RazorpayOrder, AstrologerPayout

class WalletSerializer(serializers.ModelSerializer):
    total_recharged  = serializers.SerializerMethodField()
    total_spent      = serializers.SerializerMethodField()
    total_refunded   = serializers.SerializerMethodField()

    class Meta:
        model  = Wallet
        fields = [
            'id',
            'balance',              # current available balance
            'pending_settlement',
            'total_earned',
            'total_recharged',      # sum of all recharges
            'total_spent',          # sum of all deductions
            'total_refunded',       # sum of all refunds
            'updated_at',
        ]

    def get_total_recharged(self, obj):
        from django.db.models import Sum
        result = obj.transactions.filter(
            transaction_type=Transaction.TYPE_RECHARGE
        ).aggregate(total=Sum('amount'))['total']
        return result or 0

    def get_total_spent(self, obj):
        from django.db.models import Sum
        result = obj.transactions.filter(
            transaction_type=Transaction.TYPE_DEDUCTION
        ).aggregate(total=Sum('amount'))['total']
        return result or 0

    def get_total_refunded(self, obj):
        from django.db.models import Sum
        result = obj.transactions.filter(
            transaction_type=Transaction.TYPE_REFUND
        ).aggregate(total=Sum('amount'))['total']
        return result or 0


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Transaction
        fields = [
            'id', 'transaction_type', 'amount',
            'balance_after', 'description', 'created_at',
        ]


class CreateOrderSerializer(serializers.Serializer):
    """Input: amount in INR to recharge."""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=10)


class VerifyPaymentSerializer(serializers.Serializer):
    """Input: Razorpay response after successful payment."""
    razorpay_order_id   = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature  = serializers.CharField()


class PayoutRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AstrologerPayout
        fields = ['id', 'amount', 'bank_account', 'ifsc_code', 'upi_id', 'status', 'requested_at']
        read_only_fields = ['id', 'status', 'requested_at']

    def validate_amount(self, value):
        user   = self.context['request'].user
        wallet = getattr(user, 'wallet', None)
        if not wallet or wallet.pending_settlement < value:
            raise serializers.ValidationError("Insufficient pending settlement balance.")
        if value < 500:
            raise serializers.ValidationError("Minimum payout amount is ₹500.")
        return value
