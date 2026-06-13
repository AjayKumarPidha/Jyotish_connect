import uuid
from django.db import models
from django.conf import settings


class FCMDevice(models.Model):
    """User ka phone FCM token yahan save hoga."""
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fcm_devices'
    )
    fcm_token  = models.TextField()
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fcm_devices'

    def __str__(self):
        return f"{self.user.phone} — FCM Token"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('session_request',   'Session Request'),
        ('session_accepted',  'Session Accepted'),
        ('session_ended',     'Session Ended'),
        ('low_balance',       'Low Balance'),
        ('recharge_success',  'Recharge Success'),
        ('new_review',        'New Review'),
        ('payout_approved',   'Payout Approved'),
        # ── NEW ──────────────────────────────
        ('astrologer_online', 'Astrologer Online'),
        ('chat_message',      'New Chat Message'),
        ('session_reminder',  'Session Reminder'),
        # ─────────────────────────────────────
    ]

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user              = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title             = models.CharField(max_length=100)
    body              = models.TextField()
    is_read           = models.BooleanField(default=False)
    data              = models.JSONField(default=dict, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.phone} — {self.title}"