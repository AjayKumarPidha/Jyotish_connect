import uuid
from django.db import models
from django.conf import settings


class Wallet(models.Model):
    """
    Every user has one wallet.
    Clients use it to pay for sessions.
    Astrologers receive earnings here (pending settlement).
    """
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user    = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet'
    )
    balance            = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_settlement = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallets'

    def __str__(self):
        return f"Wallet({self.user.phone}) ₹{self.balance}"

    def credit(self, amount, note=''):
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])

    def debit(self, amount, note=''):
        if self.balance < amount:
            raise ValueError("Insufficient wallet balance.")
        self.balance -= amount
        self.save(update_fields=['balance', 'updated_at'])


class RazorpayOrder(models.Model):
    """
    Razorpay order created before payment.
    Tracks the full payment lifecycle.

    PAYMENT FLOW (Industry Standard):
    1. Client creates recharge order → RazorpayOrder created
    2. Client pays on Razorpay checkout
    3. Razorpay sends webhook (payment.captured)
    4. We verify signature → Credit client wallet
    5. After session → Split: 50% company, 50% astrologer pending
    6. Admin settles astrologer earnings periodically
    """
    STATUS_CREATED   = 'created'
    STATUS_PAID      = 'paid'
    STATUS_FAILED    = 'failed'
    STATUS_REFUNDED  = 'refunded'
    STATUS_CHOICES   = [
        (STATUS_CREATED,  'Created'),
        (STATUS_PAID,     'Paid'),
        (STATUS_FAILED,   'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user                = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders'
    )
    razorpay_order_id   = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_signature  = models.CharField(max_length=256, null=True, blank=True)
    amount              = models.DecimalField(max_digits=10, decimal_places=2)   # in INR
    amount_paise        = models.IntegerField()                                  # in paise for Razorpay
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)
    notes               = models.JSONField(default=dict, blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'razorpay_orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.razorpay_order_id} ₹{self.amount} [{self.status}]"


class Transaction(models.Model):
    """
    Every money movement is recorded here.
    Provides complete audit trail.
    """
    TYPE_RECHARGE   = 'recharge'
    TYPE_DEDUCTION  = 'deduction'
    TYPE_REFUND     = 'refund'
    TYPE_SETTLEMENT = 'settlement'
    TYPE_COMMISSION  = 'commission'
    TYPE_CHOICES    = [
        (TYPE_RECHARGE,   'Recharge'),
        (TYPE_DEDUCTION,  'Session Deduction'),
        (TYPE_REFUND,     'Refund'),
        (TYPE_SETTLEMENT, 'Astrologer Settlement'),
        (TYPE_COMMISSION,  'Platform Commission'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet          = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount          = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after   = models.DecimalField(max_digits=12, decimal_places=2)
    description     = models.CharField(max_length=255, blank=True)
    order           = models.ForeignKey(
        RazorpayOrder, on_delete=models.SET_NULL, null=True, blank=True
    )
    idempotency_key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} ₹{self.amount} → {self.wallet.user.phone}"


class AstrologerPayout(models.Model):
    """
    Astrologer requests withdrawal of their pending_settlement balance.
    Admin approves and marks as paid.
    """
    STATUS_PENDING  = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_PAID     = 'paid'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES  = [
        (STATUS_PENDING,  'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_PAID,     'Paid'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    astrologer      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payouts'
    )
    amount          = models.DecimalField(max_digits=10, decimal_places=2)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    bank_account    = models.CharField(max_length=20, blank=True)
    ifsc_code       = models.CharField(max_length=11, blank=True)
    upi_id          = models.CharField(max_length=100, blank=True)
    admin_note      = models.TextField(blank=True)
    requested_at    = models.DateTimeField(auto_now_add=True)
    processed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'astrologer_payouts'
        ordering = ['-requested_at']

    def __str__(self):
        return f"Payout {self.astrologer.phone} ₹{self.amount} [{self.status}]"


class WebhookLog(models.Model):
    """Logs all incoming Razorpay webhook events for debugging and idempotency."""
    event_id    = models.CharField(max_length=100, unique=True)
    event_type  = models.CharField(max_length=100)
    payload     = models.JSONField()
    processed   = models.BooleanField(default=False)
    error       = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webhook_logs'
        ordering = ['-received_at']

    def __str__(self):
        return f"Webhook {self.event_type} [{self.event_id}]"
