from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers, status
from .models import Notification, FCMDevice


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = ['id', 'notification_type', 'title', 'body', 'is_read', 'data', 'created_at']


class NotificationListAPIView(ListAPIView):
    serializer_class   = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class MarkAllReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)
        return Response({'marked_read': count})


class UnreadCountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        return Response({'unread_count': count})


# ── NEW: FCM Token Register ──────────────────────────────────────────────────
class RegisterFCMTokenAPIView(APIView):
    """
    POST /api/notifications/register-token/
    Flutter app login hone ke baad FCM token yahan bheje.

    Request: { "fcm_token": "xyz..." }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('fcm_token')
        if not token:
            return Response(
                {'error': 'fcm_token required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Token save karo ya update karo
        FCMDevice.objects.update_or_create(
            user      = request.user,
            fcm_token = token,
            defaults  = {'is_active': True},
        )
        return Response({'success': True, 'message': 'FCM token registered.'})
# ─────────────────────────────────────────────────────────────────────────────