from django.urls import path
from .views import (
    DebugRazorpayAPIView,
    GenerateTestSignatureAPIView,
    WalletAPIView,
    CreateOrderAPIView,
    VerifyPaymentAPIView,
    WebhookAPIView,
    TransactionListAPIView,
    PayoutRequestAPIView,
    TestPaymentView,
)

urlpatterns = [
    path('',                WalletAPIView.as_view(),         name='wallet'),
    path('recharge/',       CreateOrderAPIView.as_view(),    name='wallet-recharge'),
    path('verify-payment/', VerifyPaymentAPIView.as_view(),  name='wallet-verify'),
    path('webhook/',        WebhookAPIView.as_view(),        name='razorpay-webhook'),
    path('transactions/',   TransactionListAPIView.as_view(),name='wallet-transactions'),
    path('payout/',         PayoutRequestAPIView.as_view(),  name='wallet-payout'),
    path('debug-razorpay/', DebugRazorpayAPIView.as_view(), name='debug-razorpay'),
    path('generate-signature/', GenerateTestSignatureAPIView.as_view(), name='generate-test-signature'),
    path('test-payment/',    TestPaymentView.as_view(),      name='test-payment'),
]
