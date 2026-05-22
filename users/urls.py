from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CheckPhoneAPIView,
    SendOTPAPIView,
    VerifyOTPAPIView,
    CompleteProfileAPIView,
    UserProfileAPIView,
    LogoutAPIView,
)

urlpatterns = [
    # ── Screen 1 ──────────────────────────────────────────────────────────────
    path('check-phone/',      CheckPhoneAPIView.as_view(),     name='check-phone'),
    path('send-otp/',         SendOTPAPIView.as_view(),         name='send-otp'),
    path('verify-otp/',       VerifyOTPAPIView.as_view(),       name='verify-otp'),

    # ── Screen 2 ──────────────────────────────────────────────────────────────
    path('complete-profile/', CompleteProfileAPIView.as_view(), name='complete-profile'),

    # ── Authenticated ──────────────────────────────────────────────────────────
    path('profile/',          UserProfileAPIView.as_view(),     name='user-profile'),
    path('logout/',           LogoutAPIView.as_view(),          name='logout'),
    path('token/refresh/',    TokenRefreshView.as_view(),       name='token-refresh'),
]
