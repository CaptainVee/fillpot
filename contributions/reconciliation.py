"""
Reconciliation state machine for FillPot.

The pure calculation functions (contribution_outcome, pledge_outcome) take only
Decimal values and have zero Django/ORM imports — they are unit-testable without
any database or Django setup.

The process() function wires those calculations into ORM updates and must be
called inside transaction.atomic().
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


# ── Pure outcome calculators ──────────────────────────────────────────────────

def contribution_outcome(
    intended: Decimal,
    old_total: Decimal,
    payment: Decimal,
):
    """
    Return (new_status, new_total, is_first_payment) for a contribution pot.

    new_status is one of: 'pending', 'partial', 'confirmed', 'overpaid'
    is_first_payment is True when old_total was zero.
    """
    new_total    = old_total + payment
    is_first     = old_total == Decimal(0)

    if new_total == intended:
        status = "confirmed"
    elif new_total > intended:
        status = "overpaid"
    elif new_total > Decimal(0):
        status = "partial"
    else:
        status = "pending"

    return status, new_total, is_first


def pledge_outcome(
    pledged: Decimal,
    old_total: Decimal,
    payment: Decimal,
):
    """
    Return (is_complete, new_total, is_first_payment) for a pledge pot.
    """
    new_total = old_total + payment
    is_first  = old_total == Decimal(0)
    is_complete = new_total >= pledged

    return is_complete, new_total, is_first


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ReconciliationResult:
    is_first_payment: bool
    # Contribution pot
    new_contribution_status: Optional[str] = None
    # Pledge pot
    is_newly_complete: bool = False


# ── ORM process (call inside transaction.atomic()) ────────────────────────────

def process(contributor, amount_naira: Decimal) -> ReconciliationResult:
    """
    Apply a payment to the contributor's Contribution or Pledge record.
    Updates the record in-place using F() expressions where safe, returning
    a ReconciliationResult for the caller to act on (counter updates, SSE, etc.).
    Must be called inside transaction.atomic().
    """
    from django.db.models import F
    from django.utils import timezone

    from contributions.models import Contribution, Pledge

    pot_type = contributor.pot.pot_type

    if pot_type == "contribution":
        contrib = contributor.contribution
        old_total = contrib.total_paid

        new_status, _, is_first = contribution_outcome(
            contrib.intended_amount, old_total, amount_naira
        )

        update_fields = {
            "total_paid": F("total_paid") + amount_naira,
            "status": new_status,
        }
        if new_status == "confirmed":
            update_fields["confirmed_at"] = timezone.now()

        Contribution.objects.filter(pk=contrib.pk).update(**update_fields)

        return ReconciliationResult(
            is_first_payment=is_first,
            new_contribution_status=new_status,
        )

    else:  # pledge
        pledge = contributor.pledge
        old_total = pledge.total_paid

        is_complete, _, is_first = pledge_outcome(
            pledge.pledged_amount, old_total, amount_naira
        )

        Pledge.objects.filter(pk=pledge.pk).update(
            total_paid=F("total_paid") + amount_naira,
            last_payment_at=timezone.now(),
            is_complete=is_complete,
        )

        return ReconciliationResult(
            is_first_payment=is_first,
            is_newly_complete=is_complete and not pledge.is_complete,
        )
