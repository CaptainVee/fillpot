import hashlib
import hmac
import json

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from contributions import reconciliation
from contributions.models import Contributor
from payments.client import from_kobo
from payments.models import Payment
from pots.models import Pot, Withdrawal

log = structlog.get_logger(__name__)


@csrf_exempt
@require_POST
def nomba_webhook(request):
    # ── 1. Capture raw body before any parsing ────────────────────────────────
    body = request.body

    # ── 2. HMAC-SHA256 signature verification ─────────────────────────────────
    signature = request.headers.get("nomba-signature", "")
    expected  = hmac.new(
        settings.NOMBA_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        log.warning("webhook_invalid_signature", received=signature[:16])
        return HttpResponse(status=401)

    # ── 3. Parse JSON ─────────────────────────────────────────────────────────
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = event.get("eventType") or event.get("event_type", "")
    log.info("webhook_received", event_type=event_type, request_id=event.get("requestId"))

    # ── 4. Route by event type ────────────────────────────────────────────────
    if event_type == "virtual_account.funded":
        return _handle_funded(event)

    if event_type in ("transfer.success", "transfer.failed"):
        return _handle_transfer(event, event_type)

    # Unknown event — acknowledge so Nomba doesn't retry
    return HttpResponse("ok")


# ── Handler: virtual account funded ──────────────────────────────────────────

def _handle_funded(event: dict) -> HttpResponse:
    data        = event.get("data", {})
    request_id  = event.get("requestId", "")
    va_id       = data.get("accountId", "")
    amount_kobo = int(data.get("amount") or data.get("amountReceived") or 0)
    amount_naira = from_kobo(amount_kobo)

    # ── Idempotency pre-check (cheap path) ────────────────────────────────────
    if Payment.objects.filter(nomba_request_id=request_id).exists():
        log.info("webhook_duplicate", request_id=request_id)
        return HttpResponse("ok")

    # ── Resolve contributor via indexed virtual_account_id ────────────────────
    try:
        contributor = (
            Contributor.objects
            .select_related("pot", "contribution", "pledge")
            .get(virtual_account_id=va_id)
        )
    except Contributor.DoesNotExist:
        log.warning("webhook_unknown_account", virtual_account_id=va_id)
        return HttpResponse("ok")

    pot = contributor.pot

    # Acknowledge and drop — pot is no longer active
    if pot.status != Pot.Status.ACTIVE:
        log.info("webhook_inactive_pot", pot_id=str(pot.id), status=pot.status)
        return HttpResponse("ok")

    # ── Atomic: Payment insert + reconciliation + counter updates ─────────────
    try:
        with transaction.atomic():
            try:
                payment = Payment.objects.create(
                    nomba_request_id=request_id,
                    contributor=contributor,
                    amount_naira=amount_naira,
                    amount_kobo=amount_kobo,
                    event_type=event.get("eventType", "virtual_account.funded"),
                    merchant_tx_ref=data.get("merchantTxRef", ""),
                    sender_name=data.get("senderName", ""),
                    sender_account=data.get("senderAccountNumber", ""),
                    raw_payload=event,
                )
            except IntegrityError:
                # Lost the race with a concurrent identical delivery
                log.info("webhook_duplicate_race", request_id=request_id)
                return HttpResponse("ok")

            result = reconciliation.process(contributor, amount_naira)

            # Denormalized counters — always F() to avoid read-modify-write races
            pot_updates = {"total_collected": F("total_collected") + amount_naira}
            if result.is_first_payment:
                pot_updates["contributor_count"] = F("contributor_count") + 1
            Pot.objects.filter(pk=pot.pk).update(**pot_updates)

            # Capture primitive values for the on_commit closure
            _pot_id      = str(pot.id)
            _contrib_id  = str(contributor.id)
            _payment_id  = str(payment.id)

            def _on_commit():
                from notifications.tasks import (
                    send_contribution_receipt,
                    send_organiser_notification,
                )
                # Sent synchronously — no background worker available on this host.
                # Each call is isolated so one failing send doesn't block the other.
                try:
                    send_contribution_receipt(_contrib_id, _payment_id)
                except Exception:
                    log.exception("receipt_send_error", contributor_id=_contrib_id)
                try:
                    send_organiser_notification(_pot_id, _contrib_id, _payment_id)
                except Exception:
                    log.exception("organiser_notify_error", pot_id=_pot_id)

            transaction.on_commit(_on_commit)


    except Exception:
        log.exception("webhook_processing_error", request_id=request_id)
        return HttpResponse(status=500)

    log.info(
        "webhook_processed",
        request_id=request_id,
        contributor_id=str(contributor.id),
        amount_naira=str(amount_naira),
        is_first=result.is_first_payment,
    )
    return HttpResponse("ok")


# ── Handler: transfer outcome ─────────────────────────────────────────────────

def _handle_transfer(event: dict, event_type: str) -> HttpResponse:
    data             = event.get("data", {})
    merchant_tx_ref  = data.get("merchantTxRef", "")

    if not merchant_tx_ref:
        return HttpResponse("ok")

    try:
        withdrawal = Withdrawal.objects.get(nomba_tx_ref=merchant_tx_ref)
    except Withdrawal.DoesNotExist:
        log.warning("webhook_unknown_transfer", merchant_tx_ref=merchant_tx_ref)
        return HttpResponse("ok")

    if event_type == "transfer.success":
        Withdrawal.objects.filter(pk=withdrawal.pk).update(
            status=Withdrawal.Status.SUCCESS,
            completed_at=timezone.now(),
        )
        log.info("withdrawal_succeeded", withdrawal_id=str(withdrawal.id))
    else:
        reason = data.get("responseDescription") or data.get("narration", "")
        Withdrawal.objects.filter(pk=withdrawal.pk).update(
            status=Withdrawal.Status.FAILED,
            failure_reason=reason,
            completed_at=timezone.now(),
        )
        log.warning("withdrawal_failed", withdrawal_id=str(withdrawal.id), reason=reason)

    return HttpResponse("ok")
