"""
otp_service.py
══════════════
Abstraction layer for OTP delivery.

Current mode : STATIC OTP (always "1234") — no external service needed.
Future mode  : Replace `StaticOTPBackend` with `FirebaseOTPBackend` or
               `TwilioOTPBackend` without touching views.py at all.

Usage:
    from .otp_service import otp_backend
    otp_backend.send_otp(phone)       # sends OTP, returns True/False
    otp_backend.verify_otp(phone, code)  # returns True/False
"""

import random
import string
from datetime import timedelta

from django.utils import timezone


# ─── Constants ────────────────────────────────────────────────────────────────
STATIC_OTP        = "1234"          # Change this for testing
OTP_EXPIRY_MINUTES = 10


# ─── Base class (interface) ───────────────────────────────────────────────────
class BaseOTPBackend:
    """
    Interface that all OTP backends must implement.
    Swap the backend in `otp_backend` at the bottom of this file.
    """
    def send_otp(self, phone: str) -> dict:
        """
        Trigger OTP for the given phone number.
        Returns: { "success": bool, "message": str }
        """
        raise NotImplementedError

    def verify_otp(self, phone: str, code: str) -> dict:
        """
        Verify submitted OTP code.
        Returns: { "valid": bool, "message": str }
        """
        raise NotImplementedError


# ─── Static OTP Backend (current) ────────────────────────────────────────────
class StaticOTPBackend(BaseOTPBackend):
    """
    Development/Demo backend.
    Always sends and accepts the static code defined in STATIC_OTP.
    Stores record in DB so the verify step is consistent with real backends.
    """

    def send_otp(self, phone: str) -> dict:
        from .models import OTPRecord  # local import avoids circular deps

        # Expire all previous OTPs for this phone
        OTPRecord.objects.filter(phone=phone, is_used=False).update(
            expires_at=timezone.now()
        )

        # Create a new OTP record
        OTPRecord.objects.create(
            phone      = phone,
            otp_code   = STATIC_OTP,
            expires_at = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
        )
        return {
            "success": True,
            "message": f"OTP sent to {phone}.",  # In prod: don't expose OTP here
            # Remove the next line before going to production!
            "_debug_otp": STATIC_OTP,
        }

    def verify_otp(self, phone: str, code: str) -> dict:
        from .models import OTPRecord

        record = (
            OTPRecord.objects
            .filter(phone=phone, otp_code=code, is_used=False)
            .order_by('-created_at')
            .first()
        )

        if not record:
            return {"valid": False, "message": "Invalid OTP."}

        if not record.is_valid():
            return {"valid": False, "message": "OTP has expired. Please request a new one."}

        # Mark as used
        record.is_used = True
        record.save(update_fields=['is_used'])
        return {"valid": True, "message": "OTP verified successfully."}


# ─── Firebase OTP Backend (future — plug in when ready) ──────────────────────
class FirebaseOTPBackend(BaseOTPBackend):
    """
    Production backend.
    Firebase verifies OTP on the CLIENT side; backend only validates the
    Firebase ID token. `send_otp` is a no-op here.

    To activate: set  otp_backend = FirebaseOTPBackend()  at the bottom.
    """

    def send_otp(self, phone: str) -> dict:
        # Firebase OTP is triggered client-side — nothing to do server-side
        return {"success": True, "message": "OTP sent via Firebase (client-side)."}

    def verify_otp(self, phone: str, code: str) -> dict:
        """
        `code` here is the Firebase ID Token (not a 4-digit code).
        """
        import firebase_admin
        from firebase_admin import auth as firebase_auth

        try:
            decoded = firebase_auth.verify_id_token(code)
            return {"valid": True, "message": "Firebase token verified.", "firebase_uid": decoded["uid"]}
        except firebase_admin.auth.ExpiredIdTokenError:
            return {"valid": False, "message": "Firebase token expired."}
        except Exception:
            return {"valid": False, "message": "Invalid Firebase token."}


# ─── Active backend ──────────────────────────────────────────────────────────
# ⬇ Swap this line to switch backends without touching views.py
otp_backend: BaseOTPBackend = StaticOTPBackend()
# otp_backend: BaseOTPBackend = FirebaseOTPBackend()   # ← uncomment for production
