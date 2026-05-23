from django.contrib import admin
from .models import AstrologerProfile, Review, Category, Specialty, Language


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'is_active']
    list_filter   = ['is_active']
    search_fields = ['name']


@admin.register(AstrologerProfile)
class AstrologerProfileAdmin(admin.ModelAdmin):
    list_display   = [
        'display_name', 'user', 'status', 'is_approved',
        'average_rating', 'total_sessions', 'total_earnings',
        'experience_years',
    ]
    list_filter    = ['status', 'is_approved']
    search_fields  = ['display_name', 'user__phone']
    readonly_fields = ['id', 'average_rating', 'total_sessions', 'total_earnings', 'created_at']
    filter_horizontal = ['categories']

    fieldsets = (
        ('Basic',       {'fields': ('id', 'user', 'display_name', 'bio', 'profile_photo')}),
        ('Rates',       {'fields': ('chat_rate_per_min', 'call_rate_per_min', 'video_rate_per_min')}),
        ('Tags',        {'fields': ('categories', 'specialties', 'languages', 'experience_years')}),
        ('Status',      {'fields': ('status', 'is_approved')}),
        ('Stats',       {'fields': ('average_rating', 'total_sessions', 'total_earnings')}),
        ('Timestamps',  {'fields': ('created_at',)}),
    )

    actions = ['approve_astrologers', 'reject_astrologers']

    def approve_astrologers(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, f"{queryset.count()} astrologer(s) approved.")
    approve_astrologers.short_description = "Approve selected astrologers"

    def reject_astrologers(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, f"{queryset.count()} astrologer(s) rejected.")
    reject_astrologers.short_description = "Reject selected astrologers"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = ['astrologer', 'client', 'rating', 'created_at']
    list_filter   = ['rating']
    search_fields = ['astrologer__display_name', 'client__phone']
    readonly_fields = ['id', 'created_at']
