from django.contrib import admin
from .models import Session, BillingTick


class BillingTickInline(admin.TabularInline):
    model   = BillingTick
    extra   = 0
    readonly_fields = ['amount_deducted', 'is_free_tick', 'created_at']


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display  = [
        'id', 'client', 'astrologer', 'session_type', 'status',
        'duration_minutes', 'total_amount', 'is_free_session', 'created_at',
    ]
    list_filter   = ['status', 'session_type', 'is_free_session']
    search_fields = ['client__phone', 'astrologer__display_name']
    readonly_fields = ['id', 'platform_commission', 'astrologer_earnings', 'created_at']
    inlines       = [BillingTickInline]
