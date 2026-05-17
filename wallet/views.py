import razorpay
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

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


# Razorpay test-mode client
razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


class WalletAPIView(APIView):
    """
    GET /api/wallet/
    View wallet balance and pending settlement.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_or_create_wallet(request.user)
        return Response(WalletSerializer(wallet).data)


class CreateOrderAPIView(APIView):
    """
    POST /api/wallet/recharge/
    Step 1 of payment: Create a Razorpay order.
    Client receives order_id and uses it in Razorpay checkout.

    PAYMENT LIFECYCLE:
    create_order → client pays on Razorpay → webhook fires →
    verify_payment (optional fallback) → wallet credited
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount_inr   = serializer.validated_data['amount']
        amount_paise = int(amount_inr * 100)   # Razorpay works in paise

        try:
            rz_order = razorpay_client.order.create({
                'amount':   amount_paise,
                'currency': 'INR',
                'payment_capture': 1,   # Auto-capture
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

        # Save order in DB
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
    Step 2 (fallback): Called from frontend after payment.
    Webhook is primary; this is a backup for missed webhooks.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order_id   = serializer.validated_data['razorpay_order_id']
        payment_id = serializer.validated_data['razorpay_payment_id']
        signature  = serializer.validated_data['razorpay_signature']

        # Verify signature
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
            return Response({'error': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if order.status == RazorpayOrder.STATUS_PAID:
            return Response({'message': 'Payment already verified.', 'already_done': True})

        with db_transaction.atomic():
            order.razorpay_payment_id = payment_id
            order.razorpay_signature  = signature
            order.status              = RazorpayOrder.STATUS_PAID
            order.save()

            txn = credit_wallet(
                user            = request.user,
                amount          = order.amount,
                description     = f"Wallet recharge ₹{order.amount}",
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
    Razorpay sends payment events here.
    No JWT auth — verified by Razorpay signature instead.

    Setup in Razorpay Dashboard:
    Settings → Webhooks → Add URL → https://yourdomain/api/wallet/webhook/
    Events: payment.captured, payment.failed, refund.created
    """
    permission_classes = [AllowAny]
    authentication_classes = []   # No JWT for webhooks

    def post(self, request):
        payload_body = request.body
        signature    = request.headers.get('X-Razorpay-Signature', '')

        success, message = handle_webhook(payload_body, signature)

        if success:
            return Response({'status': 'ok'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


class TransactionListAPIView(ListAPIView):
    """
    GET /api/wallet/transactions/
    Paginated transaction history for logged-in user.
    """
    serializer_class   = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        wallet = get_or_create_wallet(self.request.user)
        return Transaction.objects.filter(wallet=wallet).order_by('-created_at')


class PayoutRequestAPIView(APIView):
    """
    POST /api/wallet/payout/
    Astrologer requests withdrawal of pending_settlement balance.
    Minimum ₹500. Admin reviews and marks as paid.
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
            # Deduct from pending_settlement
            wallet = get_or_create_wallet(request.user)
            wallet.pending_settlement -= amount
            wallet.save(update_fields=['pending_settlement', 'updated_at'])

            payout = serializer.save(astrologer=request.user)

        return Response(
            PayoutRequestSerializer(payout).data,
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        payouts = AstrologerPayout.objects.filter(astrologer=request.user)
        return Response(PayoutRequestSerializer(payouts, many=True).data)
