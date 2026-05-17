from django.contrib import admin
from django.utils import timezone
from .models import Wallet, Transaction, RazorpayOrder, AstrologerPayout, WebhookLog


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display  = ['user', 'balance', 'pending_settlement', 'total_earned', 'updated_at']
    search_fields = ['user__phone']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display  = ['wallet', 'transaction_type', 'amount', 'balance_after', 'description', 'created_at']
    list_filter   = ['transaction_type']
    search_fields = ['wallet__user__phone', 'description']
    readonly_fields = ['id', 'created_at', 'idempotency_key']
    date_hierarchy = 'created_at'


@admin.register(RazorpayOrder)
class RazorpayOrderAdmin(admin.ModelAdmin):
    list_display  = ['razorpay_order_id', 'user', 'amount', 'status', 'created_at']
    list_filter   = ['status']
    search_fields = ['razorpay_order_id', 'user__phone', 'razorpay_payment_id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(AstrologerPayout)
class AstrologerPayoutAdmin(admin.ModelAdmin):
    list_display  = ['astrologer', 'amount', 'status', 'requested_at', 'processed_at']
    list_filter   = ['status']
    search_fields = ['astrologer__phone']
    readonly_fields = ['id', 'requested_at']

    actions = ['approve_payouts', 'mark_paid', 'reject_payouts']

    def approve_payouts(self, request, queryset):
        queryset.filter(status='pending').update(status='approved')
        self.message_user(request, "Selected payouts approved.")
    approve_payouts.short_description = "Approve selected payouts"

    def mark_paid(self, request, queryset):
        queryset.filter(status='approved').update(
            status='paid', processed_at=timezone.now()
        )
        self.message_user(request, "Selected payouts marked as paid.")
    mark_paid.short_description = "Mark as Paid"

    def reject_payouts(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, "Selected payouts rejected.")
    reject_payouts.short_description = "Reject selected payouts"


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display  = ['event_type', 'event_id', 'processed', 'received_at']
    list_filter   = ['event_type', 'processed']
    search_fields = ['event_id', 'event_type']
    readonly_fields = ['event_id', 'event_type', 'payload', 'processed', 'error', 'received_at']
