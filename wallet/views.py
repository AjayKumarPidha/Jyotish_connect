"""
Wallet Views
============
Handles Razorpay payment lifecycle + wallet management.

PAYMENT LIFECYCLE (end to end):
1. POST /api/wallet/recharge/         → Create Razorpay order
2. Flutter opens Razorpay checkout
3. User pays on Razorpay
4. POST /api/wallet/webhook/          → Razorpay fires webhook → wallet credited ✓
5. POST /api/wallet/verify-payment/   → Flutter calls as fallback (if webhook missed)
6. User taps Chat/Call
7. GET  /api/sessions/access-check/   → Sessions app reads wallet.balance
8. POST /api/sessions/start/          → Session begins
9. POST /api/sessions/{id}/tick/      → Per-minute debit from wallet
"""
import razorpay
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db import transaction as db_transaction

from .models import Wallet, Transaction, RazorpayOrder, AstrologerPayout
from .serializers import (
    WalletSerializer,
    TransactionSerializer,
    CreateOrderSerializer,
    VerifyPaymentSerializer,
    PayoutRequestSerializer,
)
from .utils import get_or_create_wallet, credit_wallet, verify_razorpay_signature
from .webhooks import handle_webhook
from users.permissions import IsAstrologer


# Razorpay client (test mode — swap keys for production)
razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


class WalletAPIView(APIView):
    """
    GET /api/wallet/
    Returns wallet balance + pending settlement for logged-in user.

    RESPONSE:
    {
        "id": "uuid",
        "balance": "150.00",
        "pending_settlement": "0.00",
        "total_earned": "0.00"
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_or_create_wallet(request.user)
        return Response(WalletSerializer(wallet).data)


class CreateOrderAPIView(APIView):
    """
    POST /api/wallet/recharge/
    Step 1 of payment: Create a Razorpay order.
    Flutter receives order_id and opens Razorpay checkout.

    This matches the recharge bottom sheet in Image 3.
    User selects ₹100 / ₹200 / ₹500 → taps Proceed To Pay → this API called.

    REQUEST:
    { "amount": 100 }

    RESPONSE:
    {
        "order_id": "order_xyz",
        "amount": 100,
        "currency": "INR",
        "key_id": "rzp_test_xxx",
        "user_phone": "9876543210"
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount_inr   = serializer.validated_data['amount']
        amount_paise = int(amount_inr * 100)   # Razorpay requires paise

        try:
            rz_order = razorpay_client.order.create({
                'amount':          amount_paise,
                'currency':        'INR',
                'payment_capture': 1,           # Auto-capture on payment
                'notes': {
                    'user_id': str(request.user.id),
                    'phone':   request.user.phone,
                },
            })
        except Exception as e:
            return Response(
                {'error': f'Razorpay error: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Save Razorpay order in our DB for tracking
        RazorpayOrder.objects.create(
            user              = request.user,
            razorpay_order_id = rz_order['id'],
            amount            = amount_inr,
            amount_paise      = amount_paise,
        )

        return Response({
            'order_id':   rz_order['id'],
            'amount':     amount_inr,
            'currency':   'INR',
            'key_id':     settings.RAZORPAY_KEY_ID,
            'user_phone': request.user.phone,
        })


class VerifyPaymentAPIView(APIView):
    """
    POST /api/wallet/verify-payment/
    Fallback: Called from Flutter AFTER payment completes on Razorpay.

    WHY THIS EXISTS:
    Webhooks are primary. But if webhook is delayed or missed,
    Flutter calls this immediately after user completes payment
    so wallet is credited without waiting.

    If webhook already processed it → returns already_done: True (no double credit).

    REQUEST:
    {
        "razorpay_order_id":   "order_xyz",
        "razorpay_payment_id": "pay_abc",
        "razorpay_signature":  "sig_hash"
    }

    RESPONSE:
    {
        "message": "Payment verified. Wallet credited.",
        "amount_credited": 100,
        "new_balance": 250.00
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order_id   = serializer.validated_data['razorpay_order_id']
        payment_id = serializer.validated_data['razorpay_payment_id']
        signature  = serializer.validated_data['razorpay_signature']

        # Verify Razorpay signature before doing anything
        if not verify_razorpay_signature(order_id, payment_id, signature):
            return Response(
                {'error': 'Invalid payment signature. Possible fraud attempt.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = RazorpayOrder.objects.get(
                razorpay_order_id=order_id, user=request.user
            )
        except RazorpayOrder.DoesNotExist:
            return Response(
                {'error': 'Order not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Already processed by webhook → just return success
        if order.status == RazorpayOrder.STATUS_PAID:
            wallet = get_or_create_wallet(request.user)
            return Response({
                'message':         'Payment already verified.',
                'already_done':    True,
                'amount_credited': order.amount,
                'new_balance':     wallet.balance,
            })

        # Process payment (webhook hasn't fired yet)
        with db_transaction.atomic():
            order.razorpay_payment_id = payment_id
            order.razorpay_signature  = signature
            order.status              = RazorpayOrder.STATUS_PAID
            order.save()

            credit_wallet(
                user            = request.user,
                amount          = order.amount,
                description     = f"Wallet recharge ₹{order.amount} (verified)",
                order           = order,
                idempotency_key = f"verify-{payment_id}",
            )

        wallet = get_or_create_wallet(request.user)
        return Response({
            'message':         'Payment verified. Wallet credited.',
            'amount_credited': order.amount,
            'new_balance':     wallet.balance,
        })


class WebhookAPIView(APIView):
    """
    POST /api/wallet/webhook/
    Razorpay sends payment events here automatically.

    NO JWT AUTH — authenticated via Razorpay-Signature header instead.
    Must be publicly accessible (no firewall block).

    Setup in Razorpay Dashboard:
      Settings → Webhooks → Add URL
      URL: https://yourdomain.com/api/wallet/webhook/
      Events to enable:
        ✓ payment.captured
        ✓ payment.failed
        ✓ refund.created
      Secret: set RAZORPAY_WEBHOOK_SECRET in your .env

    WHAT HAPPENS ON payment.captured:
      1. Signature verified
      2. WebhookLog created
      3. RazorpayOrder.status → 'paid'
      4. Wallet.balance += amount
      5. Transaction record created
      6. User can now start chat/call session
    """
    permission_classes    = [AllowAny]
    authentication_classes = []   # No JWT for webhooks

    def post(self, request):
        payload_body = request.body
        signature    = request.headers.get('X-Razorpay-Signature', '')

        if not signature:
            return Response(
                {'error': 'Missing X-Razorpay-Signature header'},
                status=status.HTTP_400_BAD_REQUEST
            )

        success, message = handle_webhook(payload_body, signature)

        if success:
            return Response({'status': 'ok'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


class TransactionListAPIView(ListAPIView):
    """
    GET /api/wallet/transactions/
    Paginated transaction history. Shows recharges, session debits, refunds.

    RESPONSE (paginated):
    {
        "results": [
            {
                "transaction_type": "recharge",
                "amount": "100.00",
                "balance_after": "250.00",
                "description": "Wallet recharge via Razorpay (pay_abc)",
                "created_at": "2024-01-15T10:30:00Z"
            },
            {
                "transaction_type": "deduction",
                "amount": "60.00",
                "balance_after": "190.00",
                "description": "Session abc123 — minute #1",
                "created_at": "2024-01-15T11:00:00Z"
            }
        ]
    }
    """
    serializer_class   = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        wallet = get_or_create_wallet(self.request.user)
        return Transaction.objects.filter(wallet=wallet).order_by('-created_at')


class PayoutRequestAPIView(APIView):
    """
    POST /api/wallet/payout/
    Astrologer requests withdrawal of their pending_settlement.
    Minimum ₹500. Admin approves and transfers manually.

    GET /api/wallet/payout/
    Astrologer views their payout history.
    """
    permission_classes = [IsAuthenticated, IsAstrologer]

    def post(self, request):
        serializer = PayoutRequestSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data['amount']

        with db_transaction.atomic():
            wallet = get_or_create_wallet(request.user)

            if wallet.pending_settlement < amount:
                return Response(
                    {'error': f'Insufficient pending settlement. Available: ₹{wallet.pending_settlement}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            wallet.pending_settlement -= amount
            wallet.save(update_fields=['pending_settlement', 'updated_at'])

            payout = serializer.save(astrologer=request.user)

        return Response(
            PayoutRequestSerializer(payout).data,
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        from .models import AstrologerPayout
        payouts = AstrologerPayout.objects.filter(astrologer=request.user)
        return Response(PayoutRequestSerializer(payouts, many=True).data)
    
    
    
class DebugRazorpayAPIView(APIView):
    permission_classes = [AllowAny]  # temp AllowAny for testing

    def get(self, request):
        try:
            import razorpay
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
            order = client.order.create({
                'amount': 10000,
                'currency': 'INR',
                'payment_capture': 1,
            })
            return Response({
                'status': 'SUCCESS ✅',
                'razorpay_order_id': order['id'],
                'key_used': settings.RAZORPAY_KEY_ID,
            })
        except Exception as e:
            return Response({
                'status': 'FAILED ❌',
                'error': str(e),
                'key_used': getattr(settings, 'RAZORPAY_KEY_ID', 'NOT FOUND'),
                'secret_exists': bool(getattr(settings, 'RAZORPAY_KEY_SECRET', None)),
            })
            
            
            
class GenerateTestSignatureAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        import hmac, hashlib
        
        order_id   = request.data.get('order_id')
        payment_id = request.data.get('payment_id')
        secret     = settings.RAZORPAY_KEY_SECRET

        signature = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()

        return Response({
            'order_id':   order_id,
            'payment_id': payment_id,
            'signature':  signature,
        })