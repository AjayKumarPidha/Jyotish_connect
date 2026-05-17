"""
Razorpay Webhook Handler
========================
Razorpay sends POST requests to /api/wallet/webhook/ for payment events.
We verify signature, log event, and process idempotently.

Events handled:
- payment.captured  → Credit client wallet
- payment.failed    → Mark order as failed
- refund.created    → Mark order as refunded
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
    # Step 1: Verify webhook signature
    if not verify_webhook_signature(payload_body, signature):
        logger.warning("Invalid Razorpay webhook signature")
        return False, "Invalid signature"

    try:
        payload    = json.loads(payload_body)
        event_type = payload.get('event', '')
        event_id   = payload.get('id', '')
    except json.JSONDecodeError:
        return False, "Invalid JSON payload"

    # Step 2: Idempotency — skip if already processed
    if WebhookLog.objects.filter(event_id=event_id, processed=True).exists():
        logger.info(f"Webhook {event_id} already processed. Skipping.")
        return True, "Already processed"

    # Step 3: Log the webhook
    log = WebhookLog.objects.create(
        event_id   = event_id,
        event_type = event_type,
        payload    = payload,
    )

    # Step 4: Process based on event type
    try:
        with db_transaction.atomic():
            if event_type == 'payment.captured':
                _handle_payment_captured(payload)
            elif event_type == 'payment.failed':
                _handle_payment_failed(payload)
            elif event_type == 'refund.created':
                _handle_refund_created(payload)
            else:
                logger.info(f"Unhandled webhook event: {event_type}")

        log.processed = True
        log.save(update_fields=['processed'])
        return True, "Processed"

    except Exception as e:
        log.error = str(e)
        log.save(update_fields=['error'])
        logger.error(f"Webhook processing error: {e}")
        return False, str(e)


def _handle_payment_captured(payload: dict):
    """
    Payment successful — credit client wallet.
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
        logger.error(f"Order not found: {razorpay_order_id}")
        return

    if order.status == RazorpayOrder.STATUS_PAID:
        logger.info(f"Order {razorpay_order_id} already paid. Skipping.")
        return

    # Update order
    order.razorpay_payment_id = payment_id
    order.status              = RazorpayOrder.STATUS_PAID
    order.save(update_fields=['razorpay_payment_id', 'status', 'updated_at'])

    # Credit client wallet (idempotency key = payment_id)
    credit_wallet(
        user            = order.user,
        amount          = amount_inr,
        description     = f"Wallet recharge via Razorpay ({payment_id})",
        order           = order,
        idempotency_key = f"payment-{payment_id}",
    )
    logger.info(f"Credited ₹{amount_inr} to {order.user.phone}")


def _handle_payment_failed(payload: dict):
    """Payment failed — mark order as failed."""
    payment_entity    = payload['payload']['payment']['entity']
    razorpay_order_id = payment_entity.get('order_id')

    if not razorpay_order_id:
        return

    RazorpayOrder.objects.filter(
        razorpay_order_id=razorpay_order_id
    ).update(status=RazorpayOrder.STATUS_FAILED)
    logger.info(f"Order {razorpay_order_id} marked as failed")


def _handle_refund_created(payload: dict):
    """Refund created — mark order as refunded."""
    refund_entity  = payload['payload']['refund']['entity']
    payment_id     = refund_entity.get('payment_id')

    RazorpayOrder.objects.filter(
        razorpay_payment_id=payment_id
    ).update(status=RazorpayOrder.STATUS_REFUNDED)
    logger.info(f"Payment {payment_id} marked as refunded")
