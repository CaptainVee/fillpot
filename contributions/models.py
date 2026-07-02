import uuid

from django.conf import settings
from django.db import models


class Contributor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pot = models.ForeignKey("pots.Pot", on_delete=models.PROTECT, related_name="contributors")
    # Null for guests who contributed without signing up.
    # On registration, claimed via filter(email=user.email, user=None).update(user=user).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contributions_as_contributor",
    )
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    is_anonymous = models.BooleanField(default=False)
    wants_group_notifications = models.BooleanField(default=False)
    virtual_account_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    virtual_account_number = models.CharField(max_length=10, blank=True)
    virtual_account_bank_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("pot", "email")]
        indexes = [
            models.Index(fields=["virtual_account_id"]),
        ]

    def __str__(self):
        return f"{self.full_name} → {self.pot.name}"

    @property
    def display_name(self):
        return "Anonymous" if self.is_anonymous else self.full_name


class Contribution(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PARTIAL = "partial", "Partial"
        OVERPAID = "overpaid", "Overpaid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contributor = models.OneToOneField(Contributor, on_delete=models.PROTECT, related_name="contribution")
    intended_amount = models.DecimalField(max_digits=14, decimal_places=2)
    total_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.contributor.full_name} — {self.status}"


class Pledge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contributor = models.OneToOneField(Contributor, on_delete=models.PROTECT, related_name="pledge")
    pledged_amount = models.DecimalField(max_digits=14, decimal_places=2)
    total_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_complete = models.BooleanField(default=False)
    last_payment_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_complete", "last_payment_at"]),
        ]

    def __str__(self):
        return f"{self.contributor.full_name} — {'complete' if self.is_complete else 'in progress'}"
