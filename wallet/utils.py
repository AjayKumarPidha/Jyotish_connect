import hashlib
import hmac
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import transaction as db_transaction

from .models import Wallet, Transaction, RazorpayOrder


def get_or_create_wallet(user):
    """Get or create wallet for a user."""
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


def verify_razorpay_signature(order_id, payment_id, signature):
    """
    Verify Razorpay payment signature.
    Security check to confirm payment came from Razorpay.
    """
    key_secret = settings.RAZORPAY_KEY_SECRET
    message    = f"{order_id}|{payment_id}"
    generated  = hmac.new(
        key_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated, signature)


def verify_webhook_signature(payload_body, signature):
    """Verify Razorpay webhook signature."""
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    generated = hmac.new(
        webhook_secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated, signature)


@db_transaction.atomic
def credit_wallet(user, amount, description, order=None, idempotency_key=None):
    """
    Credit amount to user wallet.
    Atomic + idempotency key prevents double crediting.
    """
    # Idempotency: skip if already processed
    if idempotency_key:
        if Transaction.objects.filter(idempotency_key=idempotency_key).exists():
            return None  # Already processed

    wallet = get_or_create_wallet(user)
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
    return txn


@db_transaction.atomic
def debit_wallet(user, amount, description, idempotency_key=None):
    """
    Debit amount from user wallet.
    Raises ValueError if insufficient balance.
    """
    wallet = get_or_create_wallet(user)

    if wallet.balance < Decimal(str(amount)):
        raise ValueError("Insufficient wallet balance.")

    wallet.balance -= Decimal(str(amount))
    wallet.save(update_fields=['balance', 'updated_at'])

    txn = Transaction.objects.create(
        wallet           = wallet,
        transaction_type = Transaction.TYPE_DEDUCTION,
        amount           = amount,
        balance_after    = wallet.balance,
        description      = description,
        idempotency_key  = idempotency_key or str(uuid.uuid4()),
    )
    return txn


@db_transaction.atomic
def split_session_earnings(session):
    """
    After session ends:
    - Full amount already deducted from client during billing ticks.
    - Split: 50% company (kept), 50% astrologer (added to pending_settlement).
    - Company keeps its 50% automatically (it never gets credited).
    - Astrologer's 50% goes to pending_settlement (not immediately withdrawable).
    - Admin settles astrologer pending_settlement on schedule.

    This is INDUSTRY STANDARD:
    ✅ Better for refunds (admin can claw back before settlement)
    ✅ Better for disputes
    ✅ Clean accounting
    ✅ Fraud prevention
    """
    commission_pct     = Decimal(str(settings.PLATFORM_COMMISSION)) / 100
    platform_cut       = session.total_amount * commission_pct
    astrologer_earning = session.total_amount - platform_cut

    # Add to astrologer pending_settlement
    astro_wallet = get_or_create_wallet(session.astrologer.user)
    astro_wallet.pending_settlement += astrologer_earning
    astro_wallet.total_earned       += astrologer_earning
    astro_wallet.save(update_fields=['pending_settlement', 'total_earned', 'updated_at'])

    # Record astrologer earning transaction
    Transaction.objects.create(
        wallet           = astro_wallet,
        transaction_type = Transaction.TYPE_SETTLEMENT,
        amount           = astrologer_earning,
        balance_after    = astro_wallet.pending_settlement,
        description      = f"Session #{session.id} earnings (pending settlement)",
        idempotency_key  = f"session-earn-{session.id}",
    )

    # Record platform commission transaction
    Transaction.objects.create(
        wallet           = astro_wallet,
        transaction_type = Transaction.TYPE_COMMISSION,
        amount           = platform_cut,
        balance_after    = astro_wallet.pending_settlement,
        description      = f"Platform commission 50% for session #{session.id}",
        idempotency_key  = f"session-commission-{session.id}",
    )

    return astrologer_earning, platform_cut
