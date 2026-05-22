"""
views.py — Jyotish Connect Authentication
==========================================

Flow:
  Screen 1 → POST /auth/check-phone/  (optional: pre-check)
           → POST /auth/send-otp/     (trigger OTP)
           → POST /auth/verify-otp/   (submit code)
                  ↓
          existing user          new user
               ↓                    ↓
         JWT tokens          temp_token (10 min)
         (login done)              ↓
                           Screen 2 → POST /auth/complete-profile/
                                           ↓
                                      JWT tokens (signup done)

Profile:
  GET  /auth/profile/    view own profile
  PUT  /auth/profile/    update profile
  POST /auth/logout/     blacklist refresh token
  POST /auth/token/refresh/  get new access token
"""

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .otp_service import otp_backend
from .tokens import get_tokens, generate_temp_token, decode_temp_token
from .serializers import (
    PhoneCheckSerializer,
    SendOTPSerializer,
    VerifyOTPSerializer,
    CompleteProfileSerializer,
    UserProfileSerializer,
)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 0 (optional) — Check if phone is registered
# POST /api/auth/check-phone/
#
# Request:  { "phone": "9999999999" }
# Response: { "exists": true, "message": "..." }
#
# Frontend uses this to show "Login" vs "Signup" label before OTP.
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
            'message': 'User found. Proceed to OTP.' if exists
                       else 'New user. Proceed to OTP.',
        })


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Send OTP
# POST /api/auth/send-otp/
#
# Request:  { "phone": "9999999999" }
# Response: { "success": true, "message": "OTP sent to +919999999999." }
#
# Currently uses StaticOTPBackend (code = 1234).
# Swap backend in otp_service.py for Firebase/Twilio.
# ─────────────────────────────────────────────────────────────────────────────
class SendOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone  = serializer.validated_data['phone']
        result = otp_backend.send_otp(phone)

        if not result.get('success'):
            return Response(
                {'error': result.get('message', 'Failed to send OTP.')},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(result, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Verify OTP
# POST /api/auth/verify-otp/
#
# Request:  { "phone": "9999999999", "otp_code": "1234" }
#
# Existing user  → { "step": "login_complete", "tokens": {...}, "user": {...} }
# New user       → { "step": "signup_incomplete", "temp_token": "..." }
# ─────────────────────────────────────────────────────────────────────────────
class VerifyOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone    = serializer.validated_data['phone']
        otp_code = serializer.validated_data['otp_code']

        # ── Verify OTP via backend ───────────────────────────────────────────
        result = otp_backend.verify_otp(phone, otp_code)
        if not result.get('valid'):
            return Response(
                {'error': result.get('message', 'OTP verification failed.')},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ── Existing user → login ────────────────────────────────────────────
        try:
            user = User.objects.get(phone=phone)
            return Response({
                'step':   'login_complete',
                'tokens': get_tokens(user),
                'user':   UserProfileSerializer(user).data,
            })

        # ── New user → temp token for Screen 2 ──────────────────────────────
        except User.DoesNotExist:
            temp_token = generate_temp_token(phone)
            return Response({
                'step':       'signup_incomplete',
                'temp_token': temp_token,
                'message':    'OTP verified. Please complete your profile.',
            }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Complete Profile (new users only)
# POST /api/auth/complete-profile/
#
# Request:
# {
#   "temp_token":         "<from verify-otp>",
#   "full_name":          "Ajay Kumar",
#   "gender":             "male",
#   "date_of_birth":      "2000-03-20",
#   "place_of_birth":     "Panna, Madhya Pradesh, India",
#   "time_of_birth":      "12:30",       ← omit if birth_time_unknown=true
#   "birth_time_unknown": false,
#   "role":               "client"
# }
#
# Response: { "step": "signup_complete", "tokens": {...}, "user": {...} }
# ─────────────────────────────────────────────────────────────────────────────
class CompleteProfileAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CompleteProfileSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # ── Validate temp token ──────────────────────────────────────────────
        try:
            token_data = decode_temp_token(data['temp_token'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        phone = token_data['phone']

        # Guard: prevent double registration
        if User.objects.filter(phone=phone).exists():
            return Response(
                {'error': 'User already registered. Please login.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Create user ──────────────────────────────────────────────────────
        user = User.objects.create_user(
            phone              = phone,
            password           = None,
            role               = data.get('role', User.ROLE_CLIENT),
            full_name          = data.get('full_name', ''),
            gender             = data.get('gender'),
            date_of_birth      = data.get('date_of_birth'),
            place_of_birth     = data.get('place_of_birth', ''),
            time_of_birth      = data.get('time_of_birth'),
            birth_time_unknown = data.get('birth_time_unknown', False),
        )

        return Response({
            'step':   'signup_complete',
            'tokens': get_tokens(user),
            'user':   UserProfileSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE — View & Edit
# GET  /api/auth/profile/  → returns own profile
# PUT  /api/auth/profile/  → updates editable fields
#
# Editable: full_name, gender, date_of_birth, place_of_birth,
#           time_of_birth, birth_time_unknown, profile_photo
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
