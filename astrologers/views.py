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
    CategorySerializer,
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
        .prefetch_related('categories')
        .distinct()
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. LIST + FILTER + SEARCH
# GET /api/astrologers/
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
            'success': True,
            'message': 'Astrologers fetched successfully.',
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
            .prefetch_related('categories'),
            pk=pk
        )
        serializer = AstrologerDetailSerializer(
            astrologer, context={'request': request}
        )
        return Response({
            'success': True,
            'message': 'Astrologer details fetched successfully.',
            'data': serializer.data
        })


# ─────────────────────────────────────────────────────────────────────────────
# 3. STATUS UPDATE
# PATCH /api/astrologers/status/
# ─────────────────────────────────────────────────────────────────────────────
class AstrologerStatusAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAstrologer]

    def patch(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        new_status = request.data.get('status', '').strip().lower()
        allowed = [
            AstrologerProfile.STATUS_ONLINE,
            AstrologerProfile.STATUS_OFFLINE,
            AstrologerProfile.STATUS_BUSY,
        ]

        if new_status not in allowed:
            return Response(
                {
                    'success': False,
                    'message': f'Invalid status. Must be one of: {allowed}',
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        profile.status = new_status
        profile.save(update_fields=['status'])
        return Response({
            'success': True,
            'message': f'Status updated to "{profile.status}" successfully.',
            'data': {'status': profile.status}
        })


# ─────────────────────────────────────────────────────────────────────────────
# 4. MY PROFILE
# GET  /api/astrologers/my-profile/
# PATCH /api/astrologers/my-profile/
# PUT   /api/astrologers/my-profile/
# ─────────────────────────────────────────────────────────────────────────────
class MyAstrologerProfileAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAstrologer]

    def get(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        serializer = AstrologerDetailSerializer(
            profile, context={'request': request}
        )
        return Response({
            'success': True,
            'message': 'Profile fetched successfully.',
            'data': serializer.data
        })

    def patch(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        serializer = AstrologerDetailSerializer(
            profile, data=request.data,
            partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Profile updated successfully.',
                'data': serializer.data
            })
        return Response(
            {
                'success': False,
                'message': 'Profile update failed. Please fix the errors.',
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    def put(self, request):
        profile = get_object_or_404(AstrologerProfile, user=request.user)
        serializer = AstrologerDetailSerializer(
            profile, data=request.data,
            partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Profile updated successfully.',
                'data': serializer.data
            })
        return Response(
            {
                'success': False,
                'message': 'Profile update failed. Please fix the errors.',
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. REVIEWS
# GET  /api/astrologers/<uuid>/review/
# POST /api/astrologers/<uuid>/review/
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
        return Response({
            'success': True,
            'message': 'Reviews fetched successfully.',
            'count': reviews.count(),
            'data': serializer.data
        })

    def post(self, request, pk):
        astrologer = get_object_or_404(AstrologerProfile, pk=pk, is_approved=True)

        # One review per client per astrologer
        if Review.objects.filter(astrologer=astrologer, client=request.user).exists():
            return Response(
                {
                    'success': False,
                    'message': 'You have already reviewed this astrologer.',
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(astrologer=astrologer, client=request.user)
            astrologer.update_rating()
            return Response(
                {
                    'success': True,
                    'message': 'Review submitted successfully.',
                    'data': serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(
            {
                'success': False,
                'message': 'Review submission failed. Please fix the errors.',
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. CATEGORY LIST
# GET /api/astrologers/categories/
# ─────────────────────────────────────────────────────────────────────────────
class CategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        categories = Category.objects.filter(is_active=True)
        serializer = CategorySerializer(
            categories, many=True, context={'request': request}
        )
        return Response({
            'success': True,
            'message': 'Categories fetched successfully.',
            'count': categories.count(),
            'data': serializer.data
        })