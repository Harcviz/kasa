from django.contrib import admin

from .models import Counterparty, CounterpartyAudit, Shareholder, Transaction, TransactionAudit


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "created_at")
    search_fields = ("name", "contact")


@admin.register(Shareholder)
class ShareholderAdmin(admin.ModelAdmin):
    list_display = ("name", "percent", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "account",
        "direction",
        "amount",
        "counterparty",
        "description",
        "is_carryover",
    )
    list_filter = ("account", "direction", "is_carryover")
    search_fields = ("description",)
    date_hierarchy = "timestamp"


@admin.register(TransactionAudit)
class TransactionAuditAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_id",
        "changed_at",
        "old_direction",
        "new_direction",
        "old_amount",
        "new_amount",
        "username",
        "ip_address",
    )
    list_filter = ("old_account", "new_account", "old_direction", "new_direction")
    search_fields = ("transaction__description",)


@admin.register(CounterpartyAudit)
class CounterpartyAuditAdmin(admin.ModelAdmin):
    list_display = ("counterparty_name", "action", "username", "ip_address", "created_at")
    list_filter = ("action",)
    search_fields = ("counterparty_name",)

# Register your models here.
