import uuid
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404

from .models import Session, BillingTick
from .serializers import SessionSerializer, StartSessionSerializer
from astrologers.models import AstrologerProfile
from wallet.utils import debit_wallet,  get_or_create_wallet
from users.permissions import IsClient, IsAstrologer, IsClientOrAstrologer

from agora_token_builder import RtcTokenBuilder
import time

FREE_SESSION_MINUTES = 5


class StartSessionAPIView(APIView):
    """
    POST /api/sessions/start/
    Client starts a session with an astrologer.

    Free Session: First-time users get 5 min free.
    Paid Session: Must have wallet balance >= 1 min rate.
    """
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request):
        serializer = StartSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        astrologer_id = serializer.validated_data['astrologer_id']
        session_type  = serializer.validated_data['session_type']

        astrologer = get_object_or_404(
            AstrologerProfile, id=astrologer_id, is_approved=True, status='online'
        )

        rate_map = {
            Session.TYPE_CHAT:  astrologer.chat_rate_per_min,
            Session.TYPE_CALL:  astrologer.call_rate_per_min,
            Session.TYPE_VIDEO: astrologer.video_rate_per_min,
        }
        rate = rate_map.get(session_type, astrologer.chat_rate_per_min)

        is_free = not request.user.has_used_free_session

        if not is_free:
            wallet = get_or_create_wallet(request.user)
            if wallet.balance < rate:
                return Response(
                    {'error': f'Minimum balance required: Rs.{rate}. Please recharge.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        session = Session.objects.create(
            client       = request.user,
            astrologer   = astrologer,
            session_type = session_type,
            status       = Session.STATUS_PENDING,
            rate_per_min = rate,
            agora_channel= str(uuid.uuid4()) if session_type in ['call', 'video'] else '',
            is_free_session = is_free,
        )

        astrologer.status = AstrologerProfile.STATUS_BUSY
        astrologer.save(update_fields=['status'])

        data = SessionSerializer(session).data
        if is_free:
            data['message'] = f'Welcome! First {FREE_SESSION_MINUTES} minutes are FREE.'
            data['free_minutes_available'] = FREE_SESSION_MINUTES
        return Response(data, status=status.HTTP_201_CREATED)


class AcceptSessionAPIView(APIView):
    """
    POST /api/sessions/<id>/accept/
    Astrologer accepts the incoming session request.
    """
    permission_classes = [IsAuthenticated, IsAstrologer]

    def post(self, request, session_id):
        session = get_object_or_404(
            Session,
            id=session_id,
            astrologer__user=request.user,
            status=Session.STATUS_PENDING,
        )
        session.status     = Session.STATUS_ACTIVE
        session.started_at = timezone.now()
        session.save(update_fields=['status', 'started_at'])
        return Response(SessionSerializer(session).data)

from wallet.utils import get_or_create_wallet  # already imported hai

class EndSessionAPIView(APIView):
    permission_classes = [IsAuthenticated, IsClientOrAstrologer]

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id, status=Session.STATUS_ACTIVE)

        is_client     = session.client == request.user
        is_astrologer = session.astrologer.user == request.user
        if not (is_client or is_astrologer):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        session.ended_at = timezone.now()
        session.status   = Session.STATUS_COMPLETED

        duration = (session.ended_at - session.started_at).total_seconds() / 60
        session.duration_minutes = Decimal(str(round(duration, 2)))

        if session.is_free_session:
            free_mins         = Decimal(str(FREE_SESSION_MINUTES))
            billable_duration = max(Decimal('0'), session.duration_minutes - free_mins)
            session.total_amount = billable_duration * session.rate_per_min
            session.client.has_used_free_session = True
            session.client.save(update_fields=['has_used_free_session'])
        else:
            session.total_amount = session.duration_minutes * session.rate_per_min

        commission_pct              = Decimal(str(settings.PLATFORM_COMMISSION)) / 100
        session.platform_commission = session.total_amount * commission_pct
        session.astrologer_earnings = session.total_amount - session.platform_commission
        session.save()

        # Astrologer ki pending_settlement mein add karo
        astro_wallet = get_or_create_wallet(session.astrologer.user)
        astro_wallet.pending_settlement += session.astrologer_earnings
        astro_wallet.total_earned       += session.astrologer_earnings
        astro_wallet.save(update_fields=['pending_settlement', 'total_earned', 'updated_at'])

        # Astrologer status online karo
        astro = session.astrologer
        astro.total_sessions += 1
        astro.status          = AstrologerProfile.STATUS_ONLINE
        astro.save(update_fields=['total_sessions', 'status'])

        return Response(SessionSerializer(session).data)

class BillingTickAPIView(APIView):
    """
    POST /api/sessions/<id>/billing-tick/
    Called every minute by the app to deduct per-minute charge.
    First 5 ticks free for first-time users.
    Auto-ends session if wallet is empty.
    """
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request, session_id):
        session = get_object_or_404(
            Session, id=session_id, client=request.user, status=Session.STATUS_ACTIVE
        )

        ticks_so_far = session.billing_ticks.count()

        # Free period
        if session.is_free_session and ticks_so_far < FREE_SESSION_MINUTES:
            BillingTick.objects.create(
                session=session, amount_deducted=Decimal('0'), is_free_tick=True
            )
            free_remaining = FREE_SESSION_MINUTES - ticks_so_far - 1
            return Response({
                'free_tick':             True,
                'free_minutes_remaining': free_remaining,
                'deducted':              0,
            })

        # Mark free session as used when paid period starts
        if session.is_free_session and not request.user.has_used_free_session:
            request.user.has_used_free_session = True
            request.user.save(update_fields=['has_used_free_session'])

        # Paid billing
        wallet = get_or_create_wallet(request.user)
        amount = session.rate_per_min

        if wallet.balance < amount:
            # Auto-end session
            session.status   = Session.STATUS_COMPLETED
            session.ended_at = timezone.now()
            session.save(update_fields=['status', 'ended_at'])
            return Response(
                {'error': 'Insufficient balance. Session ended.'},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        debit_wallet(
            user=request.user,
            amount=amount,
            description=f"Session {session_id} - 1 min {session.session_type}",
        )
        BillingTick.objects.create(session=session, amount_deducted=amount)

        return Response({
            'deducted':          amount,
            'balance_remaining': wallet.balance - amount,
        })


class SessionHistoryAPIView(ListAPIView):
    """
    GET /api/sessions/history/
    Session history for both clients and astrologers.
    """
    serializer_class   = SessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'astrologer':
            return Session.objects.filter(
                astrologer__user=user
            ).select_related('client', 'astrologer')
        return Session.objects.filter(
            client=user
        ).select_related('client', 'astrologer')
        
        
        


class AgoraTokenAPIView(APIView):
    """
    GET /api/sessions/<session_id>/agora-token/
    Call/Video ke liye Agora token generate karo
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(
            Session, id=session_id, status=Session.STATUS_ACTIVE
        )

        # Sirf client ya astrologer access kar sake
        is_client     = session.client == request.user
        is_astrologer = session.astrologer.user == request.user
        if not (is_client or is_astrologer):
            return Response(
                {'error': 'Unauthorized'},
                status=status.HTTP_403_FORBIDDEN
            )

        app_id      = settings.AGORA_APP_ID
        certificate = settings.AGORA_APP_CERTIFICATE
        channel     = session.agora_channel
        uid         = 0  # 0 = Agora khud assign karta hai
        expiry      = int(time.time()) + 3600  # 1 hour

        token = RtcTokenBuilder.buildTokenWithUid(
            app_id, certificate, channel, uid,
            RtcTokenBuilder.Role_Publisher, expiry
        )

        return Response({
            'token':   token,
            'channel': channel,
            'app_id':  app_id,
            'uid':     uid,
            'expires_in': 3600,
        })
