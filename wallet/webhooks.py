"""
Razorpay Webhook Handler
========================
Razorpay sends POST requests to /api/wallet/webhook/ for payment events.
We verify signature, log event, and process idempotently.

Events handled:
- payment.captured  → Credit client wallet
- payment.failed    → Mark order as failed
- refund.created    → Mark order as refunded

HOW IT CONNECTS TO SESSIONS:
After wallet is credited here, user's wallet.balance increases.
When user taps Chat/Call, sessions/services.py → access_check()
reads that balance and decides whether to allow the session.
No direct coupling needed — wallet balance is the bridge.
"""
import json
import logging
from django.db import transaction as db_transaction

from .models import RazorpayOrder, WebhookLog
from .utils import credit_wallet, verify_webhook_signature

logger = logging.getLogger(__name__)


def handle_webhook(payload_body: bytes, signature: str) -> tuple[bool, str]:
    """
    Main webhook handler.
    Returns (success: bool, message: str)
    """
    # Step 1: Verify Razorpay webhook signature
    if not verify_webhook_signature(payload_body, signature):
        logger.warning("Invalid Razorpay webhook signature received")
        return False, "Invalid signature"

    try:
        payload    = json.loads(payload_body)
        event_type = payload.get('event', '')
        event_id   = payload.get('id', '')
    except json.JSONDecodeError:
        return False, "Invalid JSON payload"

    # Step 2: Idempotency — skip if already processed
    # Razorpay can fire the same webhook multiple times
    if WebhookLog.objects.filter(event_id=event_id, processed=True).exists():
        logger.info(f"Webhook {event_id} already processed. Skipping.")
        return True, "Already processed"

    # Step 3: Log the raw webhook (always, even if processing fails)
    log = WebhookLog.objects.create(
        event_id   = event_id,
        event_type = event_type,
        payload    = payload,
    )

    # Step 4: Process based on event type inside atomic transaction
    try:
        with db_transaction.atomic():
            if event_type == 'payment.captured': 
                _handle_payment_captured(payload)

            elif event_type == 'payment.failed':
                _handle_payment_failed(payload)

            elif event_type == 'refund.created':
                _handle_refund_created(payload)

            else:
                logger.info(f"Unhandled webhook event type: {event_type}")

        log.processed = True
        log.save(update_fields=['processed'])
        return True, "Processed"

    except Exception as e:
        log.error = str(e)
        log.save(update_fields=['error'])
        logger.error(f"Webhook processing error for {event_id}: {e}", exc_info=True)
        return False, str(e)


def _handle_payment_captured(payload: dict):
    """
    Payment successful → credit client wallet.

    After this runs:
    - RazorpayOrder.status = 'paid'
    - Wallet.balance += amount_inr
    - Transaction record created (TYPE_RECHARGE)

    Flutter flow after this:
    User can now tap Chat/Call → access_check() will return can_start=True
    """
    payment_entity    = payload['payload']['payment']['entity']
    razorpay_order_id = payment_entity['order_id']
    payment_id        = payment_entity['id']
    amount_paise      = payment_entity['amount']
    amount_inr        = amount_paise / 100

    try:
        order = RazorpayOrder.objects.select_related('user').get(
            razorpay_order_id=razorpay_order_id
        )
    except RazorpayOrder.DoesNotExist:
        logger.error(f"RazorpayOrder not found for order_id: {razorpay_order_id}")
        return

    # Guard against duplicate webhook for same payment
    if order.status == RazorpayOrder.STATUS_PAID:
        logger.info(f"Order {razorpay_order_id} already paid. Skipping wallet credit.")
        return

    # Mark order as paid
    order.razorpay_payment_id = payment_id
    order.status              = RazorpayOrder.STATUS_PAID
    order.save(update_fields=['razorpay_payment_id', 'status', 'updated_at'])

    # Credit wallet — idempotency key prevents double-credit
    credit_wallet(
        user            = order.user,
        amount          = amount_inr,
        description     = f"Wallet recharge via Razorpay ({payment_id})",
        order           = order,
        idempotency_key = f"payment-{payment_id}",
    )

    logger.info(
        f"payment.captured: ₹{amount_inr} credited to {order.user.phone} "
        f"| payment_id={payment_id} | order={razorpay_order_id}"
    )


def _handle_payment_failed(payload: dict):
    """
    Payment failed → mark order as failed.
    User will need to retry recharge before they can start a session.
    """
    payment_entity    = payload['payload']['payment']['entity']
    razorpay_order_id = payment_entity.get('order_id')

    if not razorpay_order_id:
        logger.warning("payment.failed event missing order_id")
        return

    updated = RazorpayOrder.objects.filter(
        razorpay_order_id=razorpay_order_id
    ).update(status=RazorpayOrder.STATUS_FAILED)

    logger.info(
        f"payment.failed: order {razorpay_order_id} marked failed "
        f"(rows updated: {updated})"
    )


def _handle_refund_created(payload: dict):
    """
    Refund created → mark order as refunded.
    Note: This does NOT automatically debit the wallet back.
    Refund amount handling should be done manually or via a separate flow.
    """
    refund_entity = payload['payload']['refund']['entity']
    payment_id    = refund_entity.get('payment_id')

    if not payment_id:
        logger.warning("refund.created event missing payment_id")
        return

    updated = RazorpayOrder.objects.filter(
        razorpay_payment_id=payment_id
    ).update(status=RazorpayOrder.STATUS_REFUNDED)

    logger.info(
        f"refund.created: payment {payment_id} marked refunded "
        f"(rows updated: {updated})"
    )