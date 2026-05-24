"""
Wallet Utils
============
All wallet operations: credit, debit, pending settlement.
Used by both the wallet app (Razorpay recharge flow)
and the sessions app (per-minute billing).
"""
import hashlib
import hmac
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction as db_transaction

logger = logging.getLogger(__name__)


# ─── Razorpay Signature Verification ────────────────────────────────────────

def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
    """
    Verify Razorpay webhook signature.
    Called by WebhookAPIView before processing any event.
    """
    secret = settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8')
    expected = hmac.new(secret, payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verify payment signature from frontend (VerifyPaymentAPIView).
    Format: HMAC-SHA256 of "order_id|payment_id"
    """
    secret  = settings.RAZORPAY_KEY_SECRET.encode('utf-8')
    message = f"{order_id}|{payment_id}".encode('utf-8')
    expected = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─── Wallet Helpers ──────────────────────────────────────────────────────────

def get_or_create_wallet(user):
    """Get or create wallet for any user (client or astrologer)."""
    from .models import Wallet
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


# ─── Credit (Razorpay Recharge) ──────────────────────────────────────────────

def credit_wallet(user, amount: Decimal, description: str,
                  order=None, idempotency_key: str = None):
    """
    Credit user wallet after successful Razorpay payment.
    Called by:
      - webhooks.py → _handle_payment_captured()
      - views.py    → VerifyPaymentAPIView (fallback)

    Idempotency key prevents double-credit if webhook fires twice.
    """
    from .models import Wallet, Transaction

    # Idempotency check — skip if already processed
    if idempotency_key:
        if Transaction.objects.filter(idempotency_key=idempotency_key).exists():
            logger.info(f"Duplicate credit prevented: {idempotency_key}")
            return Transaction.objects.get(idempotency_key=idempotency_key)

    with db_transaction.atomic():
        wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
        wallet.balance += Decimal(str(amount))
        wallet.save(update_fields=['balance', 'updated_at'])

        txn = Transaction.objects.create(
            wallet           = wallet,
            transaction_type = Transaction.TYPE_RECHARGE,
            amount           = amount,
            balance_after    = wallet.balance,
            description      = description,
            order            = order,
            idempotency_key  = idempotency_key,
        )

    logger.info(f"Credited ₹{amount} to {user.phone} | key={idempotency_key}")
    return txn


# ─── Debit (Session Per-Minute Billing) ──────────────────────────────────────

def debit_wallet(user, amount: Decimal, description: str,
                 idempotency_key: str = None):
    """
    Debit user wallet for session billing.
    Called by sessions/services.py → process_billing_tick() every 60 seconds.

    Idempotency key = "session-<uuid>-tick-<minute>"
    Prevents double-deduction if tick is retried due to network error.
    """
    from .models import Wallet, Transaction

    # Idempotency check
    if idempotency_key:
        if Transaction.objects.filter(idempotency_key=idempotency_key).exists():
            logger.info(f"Duplicate debit prevented: {idempotency_key}")
            return Transaction.objects.get(idempotency_key=idempotency_key)

    with db_transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(user=user)

        if wallet.balance < Decimal(str(amount)):
            raise ValueError(
                f"Insufficient balance: ₹{wallet.balance} available, ₹{amount} required."
            )

        wallet.balance -= Decimal(str(amount))
        wallet.save(update_fields=['balance', 'updated_at'])

        txn = Transaction.objects.create(
            wallet           = wallet,
            transaction_type = Transaction.TYPE_DEDUCTION,
            amount           = amount,
            balance_after    = wallet.balance,
            description      = description,
            idempotency_key  = idempotency_key,
        )

    logger.info(f"Debited ₹{amount} from {user.phone} | key={idempotency_key}")
    return txn


# ─── Astrologer Earnings ─────────────────────────────────────────────────────

def credit_pending_settlement(astrologer, amount: Decimal, description: str,
                               idempotency_key: str = None):
    """
    Credit astrologer's pending_settlement after each billing tick.
    Called by sessions/services.py → process_billing_tick().

    50% of per-minute rate goes here.
    Admin reviews and transfers to bank periodically via PayoutRequestAPIView.

    Idempotency key = "earn-<session_uuid>-tick-<minute>"
    """
    from .models import Wallet, Transaction

    # Idempotency check
    if idempotency_key:
        if Transaction.objects.filter(idempotency_key=idempotency_key).exists():
            logger.info(f"Duplicate settlement prevented: {idempotency_key}")
            return Transaction.objects.get(idempotency_key=idempotency_key)

    with db_transaction.atomic():
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=astrologer)
        wallet.pending_settlement += Decimal(str(amount))
        wallet.total_earned       += Decimal(str(amount))
        wallet.save(update_fields=['pending_settlement', 'total_earned', 'updated_at'])

        txn = Transaction.objects.create(
            wallet           = wallet,
            transaction_type = Transaction.TYPE_SETTLEMENT,
            amount           = amount,
            balance_after    = wallet.pending_settlement,
            description      = description,
            idempotency_key  = idempotency_key,
        )

    logger.info(f"Settlement ₹{amount} credited to {astrologer.phone}")
    return txn

