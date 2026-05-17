from django.urls import path
from .views import NotificationListAPIView, MarkAllReadAPIView, UnreadCountAPIView

urlpatterns = [
    path('',             NotificationListAPIView.as_view(), name='notifications'),
    path('mark-read/',   MarkAllReadAPIView.as_view(),      name='mark-read'),
    path('unread-count/',UnreadCountAPIView.as_view(),      name='unread-count'),
]
