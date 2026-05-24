"""
Sessions Models
===============
Changes from original:
1. Added FREE_MINUTES_WARNING constant (warn at 3 min)
2. Added `warning_sent` field to Session
3. Added `end_reason` field to Session
4. BillingTick — added `minute_number` for idempotency
"""
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

    END_REASON_CLIENT      = 'client_ended'
    END_REASON_ASTROLOGER  = 'astrologer_ended'
    END_REASON_LOW_BALANCE = 'low_balance'
    END_REASON_FREE_OVER   = 'free_time_over'
    END_REASON_AUTO        = 'auto_terminated'
    END_REASON_CHOICES = [
        (END_REASON_CLIENT,      'Client Ended'),
        (END_REASON_ASTROLOGER,  'Astrologer Ended'),
        (END_REASON_LOW_BALANCE, 'Low Balance'),
        (END_REASON_FREE_OVER,   'Free Time Over'),
        (END_REASON_AUTO,        'Auto Terminated'),
    ]

    FREE_MINUTES_TOTAL   = 5
    FREE_MINUTES_WARNING = 3   # show warning after 3 min

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
    warning_sent     = models.BooleanField(default=False)
    end_reason       = models.CharField(
        max_length=30, choices=END_REASON_CHOICES, null=True, blank=True
    )
    started_at       = models.DateTimeField(null=True, blank=True)
    ended_at         = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'consultation_sessions'
        db_table  = 'sessions'
        ordering  = ['-created_at']

    def __str__(self):
        return f"Session {self.id} | {self.client.phone} -> {self.astrologer.display_name}"

    @property
    def free_ticks_used(self):
        return self.billing_ticks.filter(is_free_tick=True).count()

    @property
    def free_minutes_remaining(self):
        if not self.is_free_session:
            return 0
        return max(0, self.FREE_MINUTES_TOTAL - self.free_ticks_used)

    @property
    def should_send_warning(self):
        return (
            self.is_free_session
            and not self.warning_sent
            and self.free_ticks_used >= self.FREE_MINUTES_WARNING
        )

    @property
    def free_time_is_over(self):
        return self.is_free_session and self.free_ticks_used >= self.FREE_MINUTES_TOTAL


class BillingTick(models.Model):
    session         = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name='billing_ticks'
    )
    minute_number   = models.PositiveIntegerField(null=True)
    amount_deducted = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_free_tick    = models.BooleanField(default=False)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label       = 'consultation_sessions'
        db_table        = 'billing_ticks'
        unique_together = ('session', 'minute_number')

    def __str__(self):
        return f"Tick #{self.minute_number} | Session {self.session_id} Rs.{self.amount_deducted}"