import django_filters
from .models import AstrologerProfile


class AstrologerFilter(django_filters.FilterSet):
    """
    Filter astrologers by:
    - category (chat, call, video)
    - specialty (love, marriage, career etc.)
    - language
    - minimum experience
    - minimum rating
    """
    category        = django_filters.CharFilter(field_name='categories__name',   lookup_expr='iexact')
    specialty       = django_filters.CharFilter(field_name='specialties__name',  lookup_expr='iexact')
    language        = django_filters.CharFilter(field_name='languages__name',    lookup_expr='iexact')
    min_experience  = django_filters.NumberFilter(field_name='experience_years', lookup_expr='gte')
    min_rating      = django_filters.NumberFilter(field_name='average_rating',   lookup_expr='gte')
    status          = django_filters.CharFilter(field_name='status',             lookup_expr='iexact')
    max_chat_rate   = django_filters.NumberFilter(field_name='chat_rate_per_min', lookup_expr='lte')

    class Meta:
        model  = AstrologerProfile
        fields = ['category', 'specialty', 'language', 'min_experience', 'min_rating', 'status']
