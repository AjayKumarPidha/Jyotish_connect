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
# ─────────────────────────────────────────────────────────────────────────────
class CheckPhoneAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PhoneCheckSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed. Please check your input.',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        phone  = serializer.validated_data['phone']
        exists = User.objects.filter(phone=phone).exists()

        return Response({
            'success': True,
            'message': 'User found. Proceed to OTP.' if exists
                       else 'New user. Proceed to OTP.',
            'data': {
                'exists': exists,
            }
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Send OTP
# POST /api/auth/send-otp/
# ─────────────────────────────────────────────────────────────────────────────
class SendOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed. Please check your input.',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        phone  = serializer.validated_data['phone']
        result = otp_backend.send_otp(phone)

        if not result.get('success'):
            return Response(
                {
                    'success': False,
                    'message': result.get('message', 'Failed to send OTP.'),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # views.py — SendOTPAPIView response change karo
        return Response({
            'success': True,
            'message': 'Please verify using Firebase OTP on your device.',
            'data': {
                'firebase_project_id': 'jyotish-connect-4f75e',
            }
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Verify OTP
# POST /api/auth/verify-otp/
# ─────────────────────────────────────────────────────────────────────────────
class VerifyOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed.',
                'errors': serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        phone          = serializer.validated_data['phone']
        firebase_token = serializer.validated_data['otp_code']  # Flutter ID token bhejega

        # Firebase token verify karo
        result = otp_backend.verify_otp(phone, firebase_token)
        if not result.get('valid'):
            return Response({
                'success': False,
                'message': result.get('message', 'Verification failed.'),
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Firebase UID save karo user mein
        firebase_uid = result.get('firebase_uid')

        try:
            user = User.objects.get(phone=phone)
            # UID update karo agar nahi hai
            if firebase_uid and not user.firebase_uid:
                user.firebase_uid = firebase_uid
                user.save(update_fields=['firebase_uid'])

            return Response({
                'success': True,
                'message': 'Verification successful. Login complete.',
                'data': {
                    'step':   'login_complete',
                    'tokens': get_tokens(user),
                    'user':   UserProfileSerializer(user).data,
                }
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            temp_token = generate_temp_token(phone)
            return Response({
                'success': True,
                'message': 'Verified. Please complete your profile.',
                'data': {
                    'step':       'signup_incomplete',
                    'temp_token': temp_token,
                }
            }, status=status.HTTP_200_OK)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Complete Profile (new users only)
# POST /api/auth/complete-profile/
# ─────────────────────────────────────────────────────────────────────────────
class CompleteProfileAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CompleteProfileSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed. Please check your input.',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data

        # ── Validate temp token ──────────────────────────────────────────────
        try:
            token_data = decode_temp_token(data['temp_token'])
        except ValueError as e:
            return Response(
                {
                    'success': False,
                    'message': str(e),
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        phone = token_data['phone']

        # Guard: prevent double registration
        if User.objects.filter(phone=phone).exists():
            return Response(
                {
                    'success': False,
                    'message': 'User already registered. Please login.',
                },
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

        return Response(
            {
                'success': True,
                'message': 'Profile completed. Signup successful.',
                'data': {
                    'step':   'signup_complete',
                    'tokens': get_tokens(user),
                    'user':   UserProfileSerializer(user).data,
                }
            },
            status=status.HTTP_201_CREATED
        )


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE — View & Edit
# GET  /api/auth/profile/
# PUT  /api/auth/profile/
# ─────────────────────────────────────────────────────────────────────────────
class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'success': True,
            'message': 'Profile fetched successfully.',
            'data': UserProfileSerializer(request.user).data,
        }, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Profile update failed. Please fix the errors.',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer.save()
        return Response({
            'success': True,
            'message': 'Profile updated successfully.',
            'data': serializer.data,
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# POST /api/auth/logout/
# ─────────────────────────────────────────────────────────────────────────────
class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {
                    'success': False,
                    'message': 'Refresh token is required.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid or already blacklisted token.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'success': True,
            'message': 'Logged out successfully.',
        }, status=status.HTTP_200_OK)