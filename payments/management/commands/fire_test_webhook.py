"""
Management command to simulate a Nomba virtual_account.funded webhook locally.

Usage:
  python manage.py fire_test_webhook --contributor-id <UUID> --amount 25000
  python manage.py fire_test_webhook --virtual-account-id va_xxx --amount 5000

This signs the payload with NOMBA_WEBHOOK_SECRET and POSTs to the local
webhook endpoint, so you can test Phase 5 without ngrok.
"""

import hashlib
import hmac
import json
import uuid

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fire a fake Nomba virtual_account.funded webhook for local testing."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--contributor-id", type=str, help="UUID of the Contributor row")
        group.add_argument("--virtual-account-id", type=str, help="Nomba virtual account ID")

        parser.add_argument("--amount",  type=int, default=5000, help="Amount in naira (default: 5000)")
        parser.add_argument("--host",    type=str, default="http://localhost:8000", help="Base URL of the running server")
        parser.add_argument("--sender",  type=str, default="TEST SENDER", help="Sender name in the payload")

    def handle(self, *args, **options):
        from contributions.models import Contributor

        # Resolve virtual_account_id
        if options["contributor_id"]:
            try:
                contributor = Contributor.objects.get(id=options["contributor_id"])
            except Contributor.DoesNotExist:
                raise CommandError(f"No Contributor with id={options['contributor_id']}")

            if not contributor.virtual_account_id:
                raise CommandError(
                    f"Contributor {contributor.full_name} has no virtual_account_id yet. "
                    "Join the pot first (Nomba must be configured or use --virtual-account-id directly)."
                )
            virtual_account_id = contributor.virtual_account_id
            account_number     = contributor.virtual_account_number
            customer_ref       = str(contributor.id)
        else:
            virtual_account_id = options["virtual_account_id"]
            account_number     = "0000000000"
            customer_ref       = ""

        amount_naira = options["amount"]
        amount_kobo  = amount_naira * 100

        payload = {
            "requestId": str(uuid.uuid4()),
            "eventType": "virtual_account.funded",
            "data": {
                "accountId":           virtual_account_id,
                "accountNumber":       account_number,
                "amount":              amount_kobo,
                "amountReceived":      amount_kobo,
                "currency":            "NGN",
                "senderName":          options["sender"],
                "senderAccountNumber": "0123456789",
                "narration":           f"Test transfer — ₦{amount_naira:,}",
                "reference":           customer_ref,
                "merchantTxRef":       f"test_{uuid.uuid4().hex[:16]}",
            },
        }

        body = json.dumps(payload, separators=(",", ":")).encode()
        secret = settings.NOMBA_WEBHOOK_SECRET.encode()
        signature = hmac.new(secret, body, hashlib.sha256).hexdigest()

        url = f"{options['host'].rstrip('/')}/api/v1/webhooks/nomba/"
        self.stdout.write(f"Firing webhook → {url}")
        self.stdout.write(f"  requestId:  {payload['requestId']}")
        self.stdout.write(f"  accountId:  {virtual_account_id}")
        self.stdout.write(f"  amount:     ₦{amount_naira:,} ({amount_kobo} kobo)")

        try:
            resp = requests.post(
                url,
                data=body,
                headers={
                    "Content-Type":   "application/json",
                    "nomba-signature": signature,
                },
                timeout=10,
            )
            self.stdout.write(self.style.SUCCESS(f"  Response: {resp.status_code} {resp.text[:200]}"))
        except requests.RequestException as exc:
            raise CommandError(f"Request failed: {exc}")
