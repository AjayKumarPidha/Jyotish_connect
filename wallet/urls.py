from django.urls import path
from .views import (
    DebugRazorpayAPIView,
    WalletAPIView,
    CreateOrderAPIView,
    VerifyPaymentAPIView,
    WebhookAPIView,
    TransactionListAPIView,
    PayoutRequestAPIView,
)

urlpatterns = [
    path('',                WalletAPIView.as_view(),         name='wallet'),
    path('recharge/',       CreateOrderAPIView.as_view(),    name='wallet-recharge'),
    path('verify-payment/', VerifyPaymentAPIView.as_view(),  name='wallet-verify'),
    path('webhook/',        WebhookAPIView.as_view(),        name='razorpay-webhook'),
    path('transactions/',   TransactionListAPIView.as_view(),name='wallet-transactions'),
    path('payout/',         PayoutRequestAPIView.as_view(),  name='wallet-payout'),
    path('api/wallet/debug-razorpay/', DebugRazorpayAPIView.as_view(), name='debug-razorpay'),
]
