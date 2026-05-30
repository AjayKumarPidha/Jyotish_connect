from django.urls import path
from .views import (
    StartSessionAPIView,
    AcceptSessionAPIView,
    EndSessionAPIView,
    BillingTickAPIView,
    SessionHistoryAPIView,
    AgoraTokenAPIView
)

urlpatterns = [
    path('start/',                    StartSessionAPIView.as_view(),   name='session-start'),
    path('<uuid:session_id>/accept/', AcceptSessionAPIView.as_view(),  name='session-accept'),
    path('<uuid:session_id>/end/',    EndSessionAPIView.as_view(),     name='session-end'),
    path('<uuid:session_id>/billing-tick/', BillingTickAPIView.as_view(), name='billing-tick'),
    path('history/',                  SessionHistoryAPIView.as_view(), name='session-history'),
    path('agora-token/',              AgoraTokenAPIView.as_view(),     name='agora-token'),
    
]
