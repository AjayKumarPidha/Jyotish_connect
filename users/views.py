import jwt
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
import os
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from .models import User
from .serializers import (
    UserProfileSerializer,
    PhoneCheckSerializer,
    FirebaseVerifySerializer,
    CompleteProfileSerializer,
)


# ── lazy Firebase init — won't crash if file missing ─────────────────────────
def get_firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        cred_path = settings.FIREBASE_CREDENTIALS_PATH
        if not os.path.exists(cred_path):
            return None   # Firebase not configured yet
        cred = credentials.Certificate(cred_path)
        return firebase_admin.initialize_app(cred)



# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_tokens(user):
    """Generate JWT access + refresh tokens."""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


def generate_temp_token(phone, firebase_uid):
    """
    Short-lived token (10 min) issued after OTP verification.
    Used to authorize Screen 2 (profile completion).
    Signed with Django SECRET_KEY so it cannot be forged.
    """
    payload = {
        'phone':       phone,
        'firebase_uid': firebase_uid,
        'purpose':     'signup_step2',
        'exp':         datetime.utcnow() + timedelta(minutes=10),
        'iat':         datetime.utcnow(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def decode_temp_token(token):
    """
    Decode and validate the temp token.
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


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 1 — STEP 1
# POST /api/auth/check-phone/
#
# Request:  { "phone": "9999999999" }
# Response: { "exists": true/false, "message": "..." }
#
# Frontend uses this to decide:
#   exists=true  → show "Login" flow (still verify OTP)
#   exists=false → show "Signup" flow
# Firebase OTP is triggered CLIENT-SIDE after this call.
# ─────────────────────────────────────────────────────────────────────────────
class CheckPhoneAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PhoneCheckSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone  = serializer.validated_data['phone']
        exists = User.objects.filter(phone=phone).exists()

        return Response({
            'exists':  exists,
            'message': 'User exists. Please verify OTP to login.' if exists
                       else 'New user. Please verify OTP to continue signup.',
        })


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 1 — STEP 2
# POST /api/auth/verify-otp/
#
# Request:  { "phone": "9999999999", "firebase_token": "<idToken from Firebase>" }
#
# For EXISTING users  → returns full JWT tokens (login complete)
# For NEW users       → returns temp_token for Screen 2
# ─────────────────────────────────────────────────────────────────────────────
class VerifyOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = FirebaseVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone          = serializer.validated_data['phone']
        firebase_token = serializer.validated_data['firebase_token']
        
         # Check Firebase is configured
        app = get_firebase_app()
        if app is None:
            return Response(
                {'error': 'Firebase not configured on server.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # ── Verify Firebase ID token ─────────────────────────────────────────
        try:
            decoded = firebase_auth.verify_id_token(firebase_token)
        except firebase_auth.ExpiredIdTokenError:
            return Response(
                {'error': 'OTP expired. Please request a new one.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception:
            return Response(
                {'error': 'Invalid OTP. Verification failed.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        firebase_uid = decoded['uid']

        # ── Existing user → login complete ───────────────────────────────────
        try:
            user = User.objects.get(phone=phone)
            # Keep firebase_uid in sync
            if user.firebase_uid != firebase_uid:
                user.firebase_uid = firebase_uid
                user.save(update_fields=['firebase_uid'])

            return Response({
                'step':    'login_complete',
                'tokens':  get_tokens(user),
                'user':    UserProfileSerializer(user).data,
            })

        # ── New user → issue temp token for Screen 2 ─────────────────────────
        except User.DoesNotExist:
            temp_token = generate_temp_token(phone, firebase_uid)
            return Response({
                'step':       'signup_incomplete',
                'temp_token': temp_token,
                'message':    'OTP verified. Please complete your profile.',
            }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 2
# POST /api/auth/complete-profile/
#
# Header:  Authorization: Bearer <temp_token>   (NOT a JWT, use X-Temp-Token)
# Request: {
#   "temp_token":   "<from step 1>",
#   "full_name":    "Rahul Sharma",
#   "gender":       "male",
#   "date_of_birth":"1995-08-15",
#   "role":         "client"         (optional, default=client)
# }
# Response: full JWT tokens + user profile (signup complete)
# ─────────────────────────────────────────────────────────────────────────────
class CompleteProfileAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # ── Validate temp token ──────────────────────────────────────────────
        temp_token = request.data.get('temp_token', '').strip()
        if not temp_token:
            return Response(
                {'error': 'temp_token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_data = decode_temp_token(temp_token)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        phone        = token_data['phone']
        firebase_uid = token_data['firebase_uid']

        # Guard: don't allow re-registration
        if User.objects.filter(phone=phone).exists():
            return Response(
                {'error': 'User already registered. Please login.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Validate profile fields ──────────────────────────────────────────
        serializer = CompleteProfileSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # ── Create user ──────────────────────────────────────────────────────
        user = User.objects.create_user(
            phone        = phone,
            password     = None,                # No password — Firebase only
            firebase_uid = firebase_uid,
            role         = serializer.validated_data.get('role', User.ROLE_CLIENT),
            gender       = serializer.validated_data.get('gender'),
            date_of_birth= serializer.validated_data.get('date_of_birth'),
            full_name    = serializer.validated_data.get('full_name', ''),
        )

        return Response({
            'step':    'signup_complete',
            'tokens':  get_tokens(user),
            'user':    UserProfileSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE
# GET  /api/auth/profile/  → View own profile
# PUT  /api/auth/profile/  → Update own profile
# ─────────────────────────────────────────────────────────────────────────────
class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    def put(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# POST /api/auth/logout/
# Body: { "refresh": "<refresh_token>" }
# Blacklists the refresh token so it can't be reused.
# ─────────────────────────────────────────────────────────────────────────────
class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response(
                {'error': 'Invalid or already blacklisted token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'message': 'Logged out successfully.'})