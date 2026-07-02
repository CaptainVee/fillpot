import structlog
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

log = structlog.get_logger(__name__)


# ── Internal send helper ──────────────────────────────────────────────────────

def _send(to: str, subject: str, template_prefix: str, context: dict) -> None:
    text = render_to_string(f"{template_prefix}.txt", context)
    html = render_to_string(f"{template_prefix}.html", context)
    msg  = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
    msg.attach_alternative(html, "text/html")
    msg.send()


# ── Tasks ─────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    ignore_result=True,
)
def send_contribution_receipt(self, contributor_id: str, payment_id: str) -> None:
    """Email the contributor confirming their payment and showing their status."""
    from contributions.models import Contributor
    from payments.models import Payment

    try:
        contributor = Contributor.objects.select_related("pot").get(id=contributor_id)
        payment     = Payment.objects.get(id=payment_id)
    except (Contributor.DoesNotExist, Payment.DoesNotExist):
        log.warning("receipt_task_missing_objects",
                    contributor_id=contributor_id, payment_id=payment_id)
        return

    pot = contributor.pot

    if pot.pot_type == "contribution":
        record       = getattr(contributor, "contribution", None)
        status_label = record.get_status_display() if record else "Received"
        total_paid   = record.total_paid if record else payment.amount_naira
        intended     = record.intended_amount if record else None
    else:
        record       = getattr(contributor, "pledge", None)
        status_label = "Complete" if (record and record.is_complete) else "In progress"
        total_paid   = record.total_paid if record else payment.amount_naira
        intended     = record.pledged_amount if record else None

    context = {
        "contributor":    contributor,
        "pot":            pot,
        "payment":        payment,
        "record":         record,
        "status_label":   status_label,
        "total_paid":     total_paid,
        "intended":       intended,
        "site_url":       settings.SITE_URL if hasattr(settings, "SITE_URL") else "",
    }

    subject = f"Payment received — {pot.name}"

    try:
        _send(contributor.email, subject, "emails/contribution_receipt", context)
        log.info("receipt_sent", contributor_id=contributor_id, email=contributor.email)
    except Exception as exc:
        log.error("receipt_send_failed", contributor_id=contributor_id, error=str(exc))
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    ignore_result=True,
)
def send_organiser_notification(self, pot_id: str, contributor_id: str, payment_id: str) -> None:
    """Email the organiser when a new contribution lands."""
    from contributions.models import Contributor
    from payments.models import Payment
    from pots.models import Pot

    try:
        pot         = Pot.objects.select_related("organiser").get(id=pot_id)
        contributor = Contributor.objects.get(id=contributor_id)
        payment     = Payment.objects.get(id=payment_id)
    except (Pot.DoesNotExist, Contributor.DoesNotExist, Payment.DoesNotExist):
        log.warning("organiser_notify_task_missing_objects", pot_id=pot_id)
        return

    organiser = pot.organiser
    if not organiser.email:
        return

    context = {
        "organiser":   organiser,
        "pot":         pot,
        "contributor": contributor,
        "payment":     payment,
        "site_url":    settings.SITE_URL if hasattr(settings, "SITE_URL") else "",
    }

    subject = f"₦{payment.amount_naira:,.0f} received in {pot.name}"

    try:
        _send(organiser.email, subject, "emails/organiser_notification", context)
        log.info("organiser_notified", pot_id=pot_id, organiser=organiser.email)
    except Exception as exc:
        log.error("organiser_notify_failed", pot_id=pot_id, error=str(exc))
        raise
