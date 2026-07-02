import asyncio
import json
import uuid

import redis.asyncio as aioredis
import structlog
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PotCreateForm, WithdrawalForm
from .models import Pot, Withdrawal

log = structlog.get_logger(__name__)


def landing(request):
    if request.user.is_authenticated:
        return redirect("pots:dashboard")
    return render(request, "landing.html")


@login_required
def dashboard(request):
    pots = Pot.objects.filter(organiser=request.user).order_by("-created_at")
    return render(request, "pots/dashboard.html", {"pots": pots})


@login_required
def pot_create(request):
    if request.method == "POST":
        form = PotCreateForm(request.POST)
        if form.is_valid():
            pot = form.save(commit=False)
            pot.organiser = request.user
            pot.save()
            return redirect("pots:organiser_detail", slug=pot.slug)
    else:
        form = PotCreateForm()
    return render(request, "pots/create.html", {"form": form})


@login_required
def organiser_detail(request, slug):
    pot = get_object_or_404(Pot, slug=slug, organiser=request.user)
    contributors = pot.contributors.select_related(
        "contribution", "pledge"
    ).order_by("-created_at")
    try:
        withdrawal = pot.withdrawal
    except Withdrawal.DoesNotExist:
        withdrawal = None
    return render(request, "pots/organiser_detail.html", {
        "pot": pot,
        "contributors": contributors,
        "withdrawal": withdrawal,
    })


@login_required
def withdrawal_initiate(request, slug):
    pot = get_object_or_404(Pot, slug=slug, organiser=request.user)

    try:
        existing = pot.withdrawal
    except Withdrawal.DoesNotExist:
        existing = None

    # Read-only view for PENDING / SUCCESS states
    if existing and existing.status != Withdrawal.Status.FAILED:
        return render(request, "pots/withdrawal.html", {
            "pot": pot,
            "withdrawal": existing,
            "form": None,
        })

    if request.method == "POST":
        form = WithdrawalForm(request.POST)
        if form.is_valid():
            pot.refresh_from_db(fields=["total_collected"])

            if pot.total_collected <= 0:
                messages.error(request, "No funds available to withdraw.")
                return redirect("pots:organiser_detail", slug=slug)

            bank_code      = form.cleaned_data["bank_code"]
            account_number = form.cleaned_data["account_number"]
            account_name   = form.cleaned_data["account_name"]
            nomba_tx_ref   = f"fp-withdraw-{uuid.uuid4().hex[:16]}"

            if existing:
                # Retry path — update the failed record in place
                Withdrawal.objects.filter(pk=existing.pk).update(
                    bank_code=bank_code,
                    account_number=account_number,
                    account_name=account_name,
                    amount_naira=pot.total_collected,
                    nomba_tx_ref=nomba_tx_ref,
                    status=Withdrawal.Status.PENDING,
                    failure_reason="",
                    completed_at=None,
                )
                withdrawal = existing
            else:
                try:
                    withdrawal = Withdrawal.objects.create(
                        pot=pot,
                        organiser=request.user,
                        bank_code=bank_code,
                        account_number=account_number,
                        account_name=account_name,
                        amount_naira=pot.total_collected,
                        nomba_tx_ref=nomba_tx_ref,
                        status=Withdrawal.Status.PENDING,
                    )
                except IntegrityError:
                    messages.error(request, "A withdrawal is already in progress for this pot.")
                    return redirect("pots:organiser_detail", slug=slug)

            # Call Nomba transfer API
            try:
                from payments.client import NombaClient
                from payments.exceptions import NombaAPIError
                if not getattr(settings, "NOMBA_CLIENT_ID", ""):
                    raise NombaAPIError("Nomba integration is not configured.")
                client = NombaClient()
                client.transfer(
                    amount_naira=pot.total_collected,
                    bank_code=bank_code,
                    account_number=account_number,
                    account_name=account_name,
                    narration=f"FillPot — {pot.name}"[:100],
                    merchant_tx_ref=nomba_tx_ref,
                )
                messages.success(request, "Withdrawal initiated — funds will arrive shortly.")
                log.info("withdrawal_initiated", pot_id=str(pot.id), tx_ref=nomba_tx_ref)
            except Exception as exc:
                Withdrawal.objects.filter(pk=withdrawal.pk).update(
                    status=Withdrawal.Status.FAILED,
                    failure_reason=str(exc)[:500],
                )
                messages.error(request, f"Transfer failed: {exc}")
                log.warning("withdrawal_api_failed", pot_id=str(pot.id), exc=str(exc))

            return redirect("pots:organiser_detail", slug=slug)
    else:
        form = WithdrawalForm()

    return render(request, "pots/withdrawal.html", {
        "pot": pot,
        "form": form,
        "withdrawal": existing,  # Non-None only if FAILED (retry state)
    })


@login_required
def bank_lookup(request, slug):
    """HTMX partial — resolves account holder name from bank code + account number."""
    get_object_or_404(Pot, slug=slug, organiser=request.user)  # auth guard

    bank_code      = request.GET.get("bank_code", "").strip()
    account_number = request.GET.get("account_number", "").strip()

    if len(account_number) != 10 or not bank_code:
        return HttpResponse("")

    if not getattr(settings, "NOMBA_CLIENT_ID", ""):
        return render(request, "pots/partials/bank_name.html", {
            "account_name": "",
            "error": "Payment integration not configured.",
        })

    try:
        from payments.client import NombaClient
        client = NombaClient()
        data = client.lookup_bank_account(bank_code, account_number)
        account_name = (
            data.get("accountName")
            or data.get("account_name")
            or ""
        )
        return render(request, "pots/partials/bank_name.html", {
            "account_name": account_name,
            "error": None,
        })
    except Exception as exc:
        return render(request, "pots/partials/bank_name.html", {
            "account_name": "",
            "error": str(exc),
        })


async def pot_feed(request, slug):
    """
    Async SSE endpoint. Streams Redis pub/sub messages as Server-Sent Events.
    Requires uvicorn (ASGI) — will not work under sync Gunicorn workers.
    """
    try:
        pot = await sync_to_async(Pot.objects.get)(slug=slug)
    except Pot.DoesNotExist:
        raise Http404

    channel = f"fillpot:pot:{pot.id}:feed"

    async def event_stream():
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        log.info("sse_connected", slug=slug, channel=channel)

        try:
            loop      = asyncio.get_running_loop()
            last_ping = loop.time()

            while True:
                # Detect client disconnect (Django 4.2+ ASGI)
                if await request.is_disconnected():
                    break

                msg = await pubsub.get_message(ignore_subscribe_messages=True)
                now = loop.time()

                if msg and msg["type"] == "message":
                    yield f"data: {msg['data']}\n\n"
                    last_ping = now
                elif now - last_ping >= 25:
                    # SSE comment keeps the connection alive through proxies
                    yield ": keepalive\n\n"
                    last_ping = now
                else:
                    await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("sse_stream_error", slug=slug)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await r.aclose()
            log.info("sse_disconnected", slug=slug)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"]      = "no-cache"
    response["X-Accel-Buffering"]  = "no"   # disables nginx buffering
    return response
