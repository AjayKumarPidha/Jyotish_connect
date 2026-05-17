from django.urls import path
from .views import (
    AstrologerListAPIView,
    AstrologerDetailAPIView,
    AstrologerStatusAPIView,
    ReviewAPIView,
    MyAstrologerProfileAPIView,
    CategoryListAPIView,
    SpecialtyListAPIView,
    LanguageListAPIView,
)

urlpatterns = [
    # ── Astrologers ──────────────────────────────────────────────────────────
    path('',                   AstrologerListAPIView.as_view(),      name='astrologer-list'),
    path('<uuid:pk>/',         AstrologerDetailAPIView.as_view(),    name='astrologer-detail'),
    path('status/',            AstrologerStatusAPIView.as_view(),    name='astrologer-status'),
    path('my-profile/',        MyAstrologerProfileAPIView.as_view(), name='astrologer-my-profile'),
    path('<uuid:pk>/review/',  ReviewAPIView.as_view(),              name='astrologer-review'),

    # ── Filter options (dropdowns for frontend) ──────────────────────────────
    path('categories/',        CategoryListAPIView.as_view(),        name='category-list'),
    path('specialties/',       SpecialtyListAPIView.as_view(),       name='specialty-list'),
    path('languages/',         LanguageListAPIView.as_view(),        name='language-list'),
]