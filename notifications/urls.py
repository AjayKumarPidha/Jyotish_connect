from django.urls import path
from .views import (
    NotificationListAPIView,
    MarkAllReadAPIView,
    UnreadCountAPIView,
    RegisterFCMTokenAPIView,
)

urlpatterns = [
    path('',               NotificationListAPIView.as_view(), name='notifications'),
    path('mark-read/',     MarkAllReadAPIView.as_view(),      name='mark-read'),
    path('unread-count/',  UnreadCountAPIView.as_view(),      name='unread-count'),
    path('register-token/', RegisterFCMTokenAPIView.as_view(), name='register-fcm-token'),
]