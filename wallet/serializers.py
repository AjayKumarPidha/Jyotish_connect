from rest_framework import serializers
from .models import Wallet, Transaction, RazorpayOrder, AstrologerPayout


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Wallet
        fields = ['id', 'balance', 'pending_settlement', 'total_earned', 'updated_at']


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
