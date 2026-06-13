"""
notifications/fcm.py
====================
Firebase Cloud Messaging se push notifications bhejo.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def send_push_notification(user, title: str, body: str,
                           notification_type: str, data: dict = None):
    """
    User ke saare active FCM devices pe notification bhejo
    aur DB mein bhi save karo.
    """
    from .models import FCMDevice, Notification
    import firebase_admin
    from firebase_admin import messaging

    # DB mein save karo
    Notification.objects.create(
        user              = user,
        notification_type = notification_type,
        title             = title,
        body              = body,
        data              = data or {},
    )

    # FCM tokens lo
    tokens = FCMDevice.objects.filter(
        user=user, is_active=True
    ).values_list('fcm_token', flat=True)

    if not tokens:
        logger.info(f"No FCM tokens for user {user.phone}")
        return

    # Firebase initialize check
    try:
        firebase_admin.get_app()
    except ValueError:
        import json, os
        creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
        if creds_json:
            cred = firebase_admin.credentials.Certificate(json.loads(creds_json))
            firebase_admin.initialize_app(cred)

    # Har token pe notification bhejo
    for token in tokens:
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data={
                    'type': notification_type,
                    **(data or {}),
                },
                token=token,
            )
            messaging.send(message)
            logger.info(f"Notification sent to {user.phone}")
        except Exception as e:
            logger.error(f"FCM error for {user.phone}: {e}")
            # Invalid token → deactivate karo
            FCMDevice.objects.filter(fcm_token=token).update(is_active=False)


# ── Shortcut functions ───────────────────────────────────────────────────────

def notify_astrologer_online(client, astrologer):
    """Client ko batao ki unka astrologer online aa gaya."""
    send_push_notification(
        user              = client,
        title             = f"🔮 {astrologer.display_name} is Live!",
        body              = f"{astrologer.display_name} abhi online hain. Chat ya Call karo!",
        notification_type = 'astrologer_online',
        data              = {'astrologer_id': str(astrologer.id)},
    )

def notify_session_request(astrologer_user, client, session_type):
    """Astrologer ko batao ki session request aayi."""
    send_push_notification(
        user              = astrologer_user,
        title             = f"📞 New {session_type.title()} Request!",
        body              = f"{client.full_name or client.phone} ne {session_type} request bheja hai.",
        notification_type = 'session_request',
        data              = {'session_type': session_type},
    )

def notify_low_balance(client, balance):
    """Client ko low balance alert bhejo."""
    send_push_notification(
        user              = client,
        title             = "⚠️ Low Balance",
        body              = f"Aapka balance sirf ₹{balance} reh gaya hai. Recharge karo!",
        notification_type = 'low_balance',
        data              = {'balance': str(balance)},
    )

def notify_recharge_success(client, amount):
    """Recharge successful hone pe notification."""
    send_push_notification(
        user              = client,
        title             = "✅ Recharge Successful!",
        body              = f"₹{amount} aapke wallet mein add ho gaye.",
        notification_type = 'recharge_success',
        data              = {'amount': str(amount)},
    )

def notify_session_accepted(client, astrologer, session_type):
    """Astrologer ne session accept kiya."""
    send_push_notification(
        user              = client,
        title             = f"✅ {astrologer.display_name} Ready!",
        body              = f"{astrologer.display_name} ne aapka {session_type} accept kar liya.",
        notification_type = 'session_accepted',
        data              = {'astrologer_id': str(astrologer.id)},
    )