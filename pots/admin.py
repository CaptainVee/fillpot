from django.contrib import admin

from .models import Pot, Withdrawal


@admin.register(Pot)
class PotAdmin(admin.ModelAdmin):
    list_display = ("name", "organiser", "pot_type", "status", "total_collected", "contributor_count", "created_at")
    list_filter = ("status", "pot_type", "occasion_type")
    search_fields = ("name", "slug", "organiser__email")
    readonly_fields = ("slug", "total_collected", "contributor_count", "created_at", "updated_at")


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ("pot", "amount_naira", "status", "requested_at")
    list_filter = ("status",)
    readonly_fields = ("requested_at", "completed_at")
