from django.urls import path
from .views import (
    CheckPhoneAPIView,
    VerifyOTPAPIView,
    CompleteProfileAPIView,
    UserProfileAPIView,
    LogoutAPIView,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # ── Screen 1 ─────────────────────────────────────────────────────────────
    path('check-phone/',       CheckPhoneAPIView.as_view(),      name='check-phone'),
    path('verify-otp/',        VerifyOTPAPIView.as_view(),        name='verify-otp'),

    # ── Screen 2 ─────────────────────────────────────────────────────────────
    path('complete-profile/',  CompleteProfileAPIView.as_view(),  name='complete-profile'),

    # ── Session management ────────────────────────────────────────────────────
    path('profile/',           UserProfileAPIView.as_view(),      name='user-profile'),
    path('logout/',            LogoutAPIView.as_view(),           name='logout'),
    path('token/refresh/',     TokenRefreshView.as_view(),        name='token-refresh'),
]