from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from .models import AstrologerProfile, Category, Specialty, Language, Review
from .serializers import (
    AstrologerListSerializer,
    AstrologerDetailSerializer,
    AstrologerStatusSerializer,
    CategorySerializer,
    SpecialtySerializer,
    LanguageSerializer,
    ReviewSerializer,
)
from users.permissions import IsAstrologer, IsClient



# ─────────────────────────────────────────────────────────────────────────────
# HELPER: base approved queryset
# ─────────────────────────────────────────────────────────────────────────────
def approved_astrologers():
    return (
        AstrologerProfile.objects
        .filter(is_approved=True)
        .select_related('user')
        .prefetch_related('categories', 'specialties', 'languages')
        .distinct()
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. LIST + FILTER + SEARCH
# GET /api/astrologers/
#
# Query params:
#   ?search=ajay              → search by astrologer display_name
#   ?category=Chat            → filter by category name
#   ?specialty=Tarot          → filter by specialty name
#   ?language=Hindi           → filter by language name
#   ?status=online            → filter by online/offline/busy
#   ?min_experience=5         → experience >= 5 years
#   ?min_rating=4             → average_rating >= 4
#   ?max_chat_rate=30         → chat_rate_per_min <= 30
#   ?ordering=chat_rate_per_min | average_rating | experience_years
# ─────────────────────────────────────────────────────────────────────────────
class AstrologerListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = approved_astrologers()

        # ── Search by name ──────────────────────────────────────────────────
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(display_name__icontains=search)

        # ── Filters ─────────────────────────────────────────────────────────
        category = request.query_params.get('category', '').strip()
        if category:
            qs = qs.filter(categories__name__iexact=category)

        specialty = request.query_params.get('specialty', '').strip()
        if specialty:
            qs = qs.filter(specialties__name__iexact=specialty)

        language = request.query_params.get('language', '').strip()
        if language:
            qs = qs.filter(languages__name__iexact=language)

        status_param = request.query_params.get('status', '').strip()
        if status_param:
            qs = qs.filter(status__iexact=status_param)

        min_exp = request.query_params.get('min_experience', '').strip()
        if min_exp.isdigit():
            qs = qs.filter(experience_years__gte=int(min_exp))

        min_rating = request.query_params.get('min_rating', '').strip()
        if min_rating:
            try:
                qs = qs.filter(average_rating__gte=float(min_rating))
            except ValueError:
                pass

        max_chat_rate = request.query_params.get('max_chat_rate', '').strip()
        if max_chat_rate:
            try:
                qs = qs.filter(chat_rate_per_min__lte=float(max_chat_rate))
            except ValueError:
                pass

        # ── Ordering ────────────────────────────────────────────────────────
        ALLOWED_ORDERINGS = {
            'average_rating', '-average_rating',
            'chat_rate_per_min', '-chat_rate_per_min',
            'experience_years', '-experience_years',
            'total_sessions', '-total_sessions',
        }
        ordering = request.query_params.get('ordering', '-average_rating').strip()
        if ordering not in ALLOWED_ORDERINGS:
            ordering = '-average_rating'
        qs = qs.order_by(ordering)

        serializer = AstrologerListSerializer(
            qs, many=True, context={'request': request}
        )
        return Response({
            'count': qs.count(),
            'results': serializer.data
        })


# ─────────────────────────────────────────────────────────────────────────────
# 2. DETAIL
# GET /api/astrologers/<uuid>/
# ─────────────────────────────────────────────────────────────────────────────
class AstrologerDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        astrologer = get_object_or_404(
            AstrologerProfile.objects
            .filter(is_approved=True)
            .select_related('user')
            .prefetch_related('categories', 'specialties', 'languages', 'reviews__client'),
            pk=pk
        )
        serializer = AstrologerDetailSerializer(
            astrologer, context={'request': request}
        )
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# 3. STATUS UPDATE (astrologer sets online/offline/busy)
# PATCH /api/astrologers/status/
# Body: { "status": "online" }
# ─────────────────────────────────────────────────────────────────────────────
class AstrologerStatusAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAstrologer]

    def patch(self, request):
        profile = get_object_or_404(
            AstrologerProfile, user=request.user
        )
        new_status = request.data.get('status', '').strip().lower()
        allowed = [AstrologerProfile.STATUS_ONLINE,
                   AstrologerProfile.STATUS_OFFLINE,
                   AstrologerProfile.STATUS_BUSY]

        if new_status not in allowed:
            return Response(
                {'error': f'Status must be one of: {allowed}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        profile.status = new_status
        profile.save(update_fields=['status'])
        return Response({'status': profile.status})


# ─────────────────────────────────────────────────────────────────────────────
# 4. MY PROFILE (astrologer views/updates their own profile)
# GET  /api/astrologers/my-profile/
# PATCH /api/astrologers/my-profile/
# ─────────────────────────────────────────────────────────────────────────────
class MyAstrologerProfileAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAstrologer]

    def get(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        serializer = AstrologerDetailSerializer(
            profile, context={'request': request}
        )
        return Response(serializer.data)

    def patch(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        serializer = AstrologerDetailSerializer(
            profile, data=request.data,
            partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# 5. REVIEWS
# GET  /api/astrologers/<uuid>/review/   → list reviews of an astrologer
# POST /api/astrologers/<uuid>/review/   → client submits a review
# ─────────────────────────────────────────────────────────────────────────────
class ReviewAPIView(APIView):

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsClient()]

    def get(self, request, pk):
        astrologer = get_object_or_404(AstrologerProfile, pk=pk, is_approved=True)
        reviews = Review.objects.filter(astrologer=astrologer).select_related('client')
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        astrologer = get_object_or_404(AstrologerProfile, pk=pk, is_approved=True)

        # One review per client per astrologer
        if Review.objects.filter(astrologer=astrologer, client=request.user).exists():
            return Response(
                {'error': 'You have already reviewed this astrologer.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(astrologer=astrologer, client=request.user)
            astrologer.update_rating()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# 6. CATEGORY LIST  ← NEW
# GET /api/astrologers/categories/
# Returns all active categories (Chat, Call, Video etc.)
# ─────────────────────────────────────────────────────────────────────────────
class CategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        categories = Category.objects.filter(is_active=True)
        serializer = CategorySerializer(
            categories, many=True, context={'request': request}
        )
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# 7. SPECIALTY LIST  ← NEW
# GET /api/astrologers/specialties/
# ─────────────────────────────────────────────────────────────────────────────
class SpecialtyListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        specialties = Specialty.objects.filter(is_active=True)
        serializer = SpecialtySerializer(specialties, many=True)
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# 8. LANGUAGE LIST  ← NEW
# GET /api/astrologers/languages/
# ─────────────────────────────────────────────────────────────────────────────
class LanguageListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        languages = Language.objects.all()
        serializer = LanguageSerializer(languages, many=True)
        return Response(serializer.data)


class MyAstrologerProfileAPIView(APIView):
    """
    GET  /api/astrologers/my-profile/
    PUT  /api/astrologers/my-profile/
    Astrologer views/updates their own profile.
    """
    permission_classes = [IsAuthenticated, IsAstrologer]

    def get(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        return Response(AstrologerDetailSerializer(profile).data)

    def put(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        serializer = AstrologerDetailSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)
