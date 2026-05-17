import uuid
from django.db import models
from django.conf import settings


class Session(models.Model):
    TYPE_CHAT  = 'chat'
    TYPE_CALL  = 'call'
    TYPE_VIDEO = 'video'
    TYPE_CHOICES = [
        (TYPE_CHAT,  'Chat'),
        (TYPE_CALL,  'Call'),
        (TYPE_VIDEO, 'Video'),
    ]

    STATUS_PENDING   = 'pending'
    STATUS_ACTIVE    = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES   = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_ACTIVE,    'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client           = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_sessions'
    )
    astrologer       = models.ForeignKey(
        'astrologers.AstrologerProfile', on_delete=models.CASCADE, related_name='astrologer_sessions'
    )
    session_type     = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_CHAT)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rate_per_min     = models.DecimalField(max_digits=8, decimal_places=2)
    duration_minutes = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    platform_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    astrologer_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_free_session  = models.BooleanField(default=False)
    agora_channel    = models.CharField(max_length=100, blank=True)
    started_at       = models.DateTimeField(null=True, blank=True)
    ended_at         = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'consultation_sessions'
        db_table  = 'sessions'
        ordering  = ['-created_at']

    def __str__(self):
        return f"Session {self.id} | {self.client.phone} → {self.astrologer.display_name}"


class BillingTick(models.Model):
    """Records each per-minute billing deduction."""
    session          = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='billing_ticks')
    amount_deducted  = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_free_tick     = models.BooleanField(default=False)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'consultation_sessions'
        db_table  = 'billing_ticks'

    def __str__(self):
        return f"Tick {self.session_id} ₹{self.amount_deducted}"
