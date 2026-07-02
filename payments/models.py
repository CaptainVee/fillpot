import uuid

from django.db import models


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nomba_request_id = models.CharField(max_length=200, unique=True)
    contributor = models.ForeignKey(
        "contributions.Contributor", on_delete=models.PROTECT, related_name="payments"
    )
    amount_naira = models.DecimalField(max_digits=14, decimal_places=2)
    amount_kobo = models.BigIntegerField()
    event_type = models.CharField(max_length=50)
    merchant_tx_ref = models.CharField(max_length=200, unique=True, blank=True)
    sender_name = models.CharField(max_length=200, blank=True)
    sender_account = models.CharField(max_length=20, blank=True)
    raw_payload = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["contributor"]),
            models.Index(fields=["processed_at"]),
        ]

    def __str__(self):
        return f"₦{self.amount_naira} — {self.nomba_request_id[:12]}"
