from django.db import models
from django.utils import timezone


class Counterparty(models.Model):
    """Cari hesap kaydı."""

    name = models.CharField(max_length=120)
    contact = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Cari"
        verbose_name_plural = "Cariler"

    def __str__(self) -> str:
        return self.name


class Transaction(models.Model):
    """Kasa hareketi."""

    class Direction(models.TextChoices):
        IN = "IN", "Gelir"
        OUT = "OUT", "Gider"

    class Account(models.TextChoices):
        CASH = "CASH", "Nakit"
        BANK = "BANK", "Banka"

    direction = models.CharField(max_length=3, choices=Direction.choices)
    account = models.CharField(max_length=5, choices=Account.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    counterparty = models.ForeignKey(
        Counterparty, null=True, blank=True, on_delete=models.SET_NULL
    )
    timestamp = models.DateTimeField(default=timezone.now)
    is_carryover = models.BooleanField(default=False)
    approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp", "-id"]
        verbose_name = "Hareket"
        verbose_name_plural = "Hareketler"

    def __str__(self) -> str:
        return f"{self.get_account_display()} {self.get_direction_display()} {self.amount}"


class CashCategory(models.Model):
    """Nakit kasa için hızlı gelir/gider kalemi."""

    name = models.CharField(max_length=120)
    direction = models.CharField(max_length=3, choices=Transaction.Direction.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("name", "direction")
        verbose_name = "Nakit Kasa Kalemi"
        verbose_name_plural = "Nakit Kasa Kalemleri"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_direction_display()})"


class TransactionAudit(models.Model):
    """Hareket düzenleme/silme kayıtları."""

    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name="audits")
    old_direction = models.CharField(max_length=3)
    new_direction = models.CharField(max_length=3)
    old_account = models.CharField(max_length=5)
    new_account = models.CharField(max_length=5)
    old_amount = models.DecimalField(max_digits=12, decimal_places=2)
    new_amount = models.DecimalField(max_digits=12, decimal_places=2)
    old_description = models.CharField(max_length=255, blank=True)
    new_description = models.CharField(max_length=255, blank=True)
    old_counterparty = models.CharField(max_length=120, blank=True)
    new_counterparty = models.CharField(max_length=120, blank=True)
    username = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "Hareket Log"
        verbose_name_plural = "Hareket Logları"

    def __str__(self) -> str:
        return f"Düzenleme #{self.id} - {self.transaction_id}"


class CounterpartyAudit(models.Model):
    """Cari ekleme/silme kayıtları."""

    counterparty_name = models.CharField(max_length=120)
    action = models.CharField(max_length=20)  # created / deleted
    username = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Cari Log"
        verbose_name_plural = "Cari Logları"

    def __str__(self) -> str:
        return f"{self.counterparty_name} - {self.action}"
