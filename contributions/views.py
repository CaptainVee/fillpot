import structlog
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from payments.client import NombaClient
from payments.exceptions import NombaAPIError
from pots.models import Pot

from .forms import ContributorJoinForm
from .models import Contribution, Contributor, Pledge

log = structlog.get_logger(__name__)


def public_pot(request, slug):
    pot = get_object_or_404(Pot, slug=slug)
    recent_contributors = (
        pot.contributors
        .filter(virtual_account_id__isnull=False)
        .order_by("-created_at")[:20]
    )
    return render(request, "pots/public_pot.html", {
        "pot": pot,
        "recent_contributors": recent_contributors,
    })


def join_pot(request, slug):
    pot = get_object_or_404(Pot, slug=slug)

    if pot.status != Pot.Status.ACTIVE:
        return render(request, "contributions/pot_closed.html", {"pot": pot})

    if request.method == "POST":
        form = ContributorJoinForm(request.POST, pot=pot)
        if form.is_valid():
            email = form.cleaned_data["email"]

            # Returning contributor — show their existing virtual account
            if getattr(form, "already_joined", False):
                contributor = Contributor.objects.get(pot=pot, email=email)
                return redirect("pots:contributions:account_displayed", slug=slug, contributor_id=contributor.id)

            # New contributor
            contributor = Contributor.objects.create(
                pot=pot,
                full_name=form.cleaned_data["full_name"],
                email=email,
                is_anonymous=form.cleaned_data["is_anonymous"],
                wants_group_notifications=form.cleaned_data["wants_group_notifications"],
                user=request.user if request.user.is_authenticated else None,
            )

            amount = form.cleaned_data["amount"]
            if pot.pot_type == Pot.PotType.CONTRIBUTION:
                Contribution.objects.create(contributor=contributor, intended_amount=amount)
            else:
                Pledge.objects.create(contributor=contributor, pledged_amount=amount)

            # Provision a dedicated virtual account via Nomba
            _provision_virtual_account(contributor)

            return redirect("pots:contributions:account_displayed", slug=slug, contributor_id=contributor.id)
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {"full_name": request.user.full_name, "email": request.user.email}
        form = ContributorJoinForm(pot=pot, initial=initial)

    return render(request, "contributions/join.html", {"pot": pot, "form": form})


def account_displayed(request, slug, contributor_id):
    pot = get_object_or_404(Pot, slug=slug)
    contributor = get_object_or_404(Contributor, id=contributor_id, pot=pot)

    record = None
    if pot.pot_type == Pot.PotType.CONTRIBUTION:
        record = getattr(contributor, "contribution", None)
    else:
        record = getattr(contributor, "pledge", None)

    return render(request, "contributions/account_displayed.html", {
        "pot": pot,
        "contributor": contributor,
        "record": record,
    })


# ── helpers ──────────────────────────────────────────────────────────────────

def _provision_virtual_account(contributor: Contributor) -> None:
    """
    Call Nomba to create a virtual account and store the NUBAN on the contributor.
    Failures are logged but not raised — the user still gets the account_displayed
    page with a "setting up" placeholder so the join flow never hard-errors.
    Skipped entirely when NOMBA_CLIENT_ID is not configured (e.g. local dev without credentials).
    """
    if not settings.NOMBA_CLIENT_ID:
        log.info("nomba_skipped_no_credentials", contributor_id=str(contributor.id))
        return

    try:
        client = NombaClient()
        result = client.create_virtual_account(
            customer_name=contributor.full_name,
            email=contributor.email,
            customer_ref=str(contributor.id),
        )

        contributor.virtual_account_id      = result.get("accountId") or result.get("accountHolderId")
        contributor.virtual_account_number  = result.get("accountNumber") or result.get("bankAccountNumber", "")
        contributor.virtual_account_bank_name = result.get("bankName", "")
        contributor.save(update_fields=[
            "virtual_account_id",
            "virtual_account_number",
            "virtual_account_bank_name",
        ])

        log.info(
            "virtual_account_created",
            contributor_id=str(contributor.id),
            account_number=contributor.virtual_account_number,
        )

    except NombaAPIError as exc:
        log.error(
            "virtual_account_failed",
            contributor_id=str(contributor.id),
            error=str(exc),
            status_code=exc.status_code,
            response_body=exc.response_body,
        )
        # Contributor row is already saved — they'll see the "setting up" placeholder.
