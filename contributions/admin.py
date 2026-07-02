from django.contrib import admin

from .models import Contribution, Contributor, Pledge


class ContributionInline(admin.StackedInline):
    model = Contribution
    extra = 0
    # readonly_fields = ("total_paid", "status", "confirmed_at", "created_at", "updated_at")


class PledgeInline(admin.StackedInline):
    model = Pledge
    extra = 0
    readonly_fields = ("total_paid", "is_complete", "last_payment_at", "created_at", "updated_at")


@admin.register(Contributor)
class ContributorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "pot", "virtual_account_number", "created_at")
    list_filter = ("pot__pot_type", "is_anonymous")
    search_fields = ("full_name", "email", "virtual_account_id", "virtual_account_number")
    # readonly_fields = ("id", "virtual_account_id", "virtual_account_number", "virtual_account_bank_name", "created_at")xs
    inlines = [ContributionInline, PledgeInline]


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ("contributor", "intended_amount", "total_paid", "status", "updated_at")
    list_filter = ("status",)
    readonly_fields = ("total_paid", "confirmed_at", "created_at", "updated_at")


@admin.register(Pledge)
class PledgeAdmin(admin.ModelAdmin):
    list_display = ("contributor", "pledged_amount", "total_paid", "is_complete", "last_payment_at")
    list_filter = ("is_complete",)
    readonly_fields = ("total_paid", "last_payment_at", "created_at", "updated_at")
