"""
tokens.py
─────────
JWT helpers. Kept separate so views.py stays clean.
"""
import jwt
from datetime import datetime, timedelta

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens(user) -> dict:
    """Generate standard SimpleJWT access + refresh tokens."""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


def generate_temp_token(phone: str) -> str:
    """
    Short-lived token (10 min) issued after OTP verification for NEW users.
    Used to authorize the /complete-profile/ endpoint (Screen 2).
    Signed with SECRET_KEY — cannot be forged.
    """
    payload = {
        'phone':   phone,
        'purpose': 'signup_step2',
        'exp':     datetime.utcnow() + timedelta(minutes=10),
        'iat':     datetime.utcnow(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def decode_temp_token(token: str) -> dict:
    """
    Decode & validate temp token.
    Returns payload dict or raises ValueError.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        if payload.get('purpose') != 'signup_step2':
            raise ValueError('Invalid token purpose.')
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError('Token expired. Please verify OTP again.')
    except jwt.InvalidTokenError:
        raise ValueError('Invalid token.')



