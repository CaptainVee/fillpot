import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Pot(models.Model):
    class PotType(models.TextChoices):
        CONTRIBUTION = "contribution", "Contribution"
        PLEDGE = "pledge", "Pledge"

    class OccasionType(models.TextChoices):
        WEDDING = "wedding", "Wedding"
        BIRTHDAY = "birthday", "Birthday"
        BURIAL = "burial", "Burial"
        CHURCH = "church", "Church / Religious"
        COOPERATIVE = "cooperative", "Cooperative"
        FUNDRAISER = "fundraiser", "Fundraiser"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organiser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pots"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    pot_type = models.CharField(max_length=20, choices=PotType.choices, default=PotType.CONTRIBUTION)
    occasion_type = models.CharField(max_length=20, choices=OccasionType.choices, default=OccasionType.OTHER)
    slug = models.SlugField(max_length=30, unique=True)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    total_collected = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    contributor_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["organiser", "status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:12]
            suffix = uuid.uuid4().hex[:6]
            self.slug = f"{base}-{suffix}" if base else suffix
        super().save(*args, **kwargs)


class Withdrawal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pot = models.OneToOneField(Pot, on_delete=models.PROTECT, related_name="withdrawal")
    organiser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="withdrawals"
    )
    bank_code = models.CharField(max_length=10)
    account_number = models.CharField(max_length=10)
    account_name = models.CharField(max_length=200)
    amount_naira = models.DecimalField(max_digits=14, decimal_places=2)
    nomba_tx_ref = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Withdrawal for {self.pot.name} — {self.status}"
