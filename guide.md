# Nomba API Developer Guide

## Environments

| Environment | Base URL | Use |
|---|---|---|
| Sandbox | `https://sandbox.api.nomba.com/v1` | All hackathon work |
| Production | `https://api.nomba.com/v1` | Post-certification, after KYC |

### Test Credentials

| Scenario | Card Number |
|---|---|
| Success | `5060 6666 6666 6666 666` — any future expiry, any CVV |
| Insufficient funds | `5060 6666 6666 6666 674` |

**Test bank:** Wema Bank, account `0000000000` — accepts any inbound transfer.

---

## Authentication

Nomba uses OAuth 2.0 `client_credentials` for server-to-server calls. Exchange your `clientId` and `clientSecret` for a short-lived access token (1 hour), then attach it as a `Bearer` token on every request alongside the `accountId` header.

| Endpoint | Description |
|---|---|
| `POST /auth/token/issue` | Issue an access token |
| `POST /auth/token/refresh` | Refresh before expiry |

```python
import os, requests

res = requests.post(
    "https://api.nomba.com/v1/auth/token/issue",
    headers={
        "Content-Type": "application/json",
        "accountId": os.environ["NOMBA_ACCOUNT_ID"],
    },
    json={
        "grant_type": "client_credentials",
        "client_id": os.environ["NOMBA_CLIENT_ID"],
        "client_secret": os.environ["NOMBA_CLIENT_SECRET"],
    },
)
print("access_token:", res.json()["data"]["access_token"])
```

> **Cache your tokens.** Tokens are valid for 60 minutes. Cache in memory or Redis and refresh at the 55-minute mark — do not request a fresh token per call.

---

## Sub-accounts

Sub-accounts split a single Nomba merchant into many logical accounts — useful for marketplaces, multi-tenant SaaS, or any product where funds must be tracked per seller, branch, or project. Each sub-account has its own balance and its own virtual accounts.

| Endpoint | Description |
|---|---|
| `POST /accounts/sub-accounts` | Create a new sub-account |
| `GET /accounts/sub-accounts` | List sub-accounts under your parent |
| `GET /accounts/sub-accounts/{id}/balance` | Fetch available balance |

```python
sub = nomba.post("/accounts/sub-accounts", json={
    "accountName": "Seller — Adaeze Kitchen",
    "accountRef": "seller_adaeze_001",
})
```

> **Use stable refs.** Pass your own `accountRef` so you can look up Nomba sub-accounts from your database without storing Nomba IDs as primary keys.

---

## Checkout (Hosted Payment Page)

The Checkout API generates a hosted payment page. POST the order, get a `checkoutUrl` back, and redirect the customer. Nomba handles card entry, 3-D Secure, OTPs, and PCI scope. You receive a webhook when payment completes.

| Endpoint | Description |
|---|---|
| `POST /checkout/order` | Create a hosted checkout session |
| `GET /checkout/order/{orderReference}` | Look up session status |

```python
from uuid import uuid4

order = nomba.post("/checkout/order", json={
    "order": {
        "orderReference": f"ord_{uuid4()}",
        "amount": 250000,          # in kobo — ₦2,500.00
        "currency": "NGN",
        "callbackUrl": "https://yourapp.com/payment/return",
        "customerId": "cus_8821",
        "customerEmail": "ada@example.com",
    },
})
return redirect(order["data"]["checkoutUrl"])
```

**Response:**
```json
{
  "code": "00",
  "description": "Success",
  "data": {
    "orderReference": "ord_demo_001",
    "checkoutUrl": "https://checkout.nomba.com/pay/ord_demo_001",
    "amount": "250000",
    "currency": "NGN",
    "status": "pending"
  }
}
```

> **Amounts are in kobo.** ₦1.00 = 100 kobo. Always multiply naira by 100 before sending.

### Checkout Flow

1. Customer clicks **Pay** in your app
2. Your server POSTs `/checkout/order` and receives a `checkoutUrl`
3. You redirect the customer to the `checkoutUrl`
4. Customer enters card details and completes 3-D Secure on Nomba's hosted page
5. Nomba sends a `payment_success` webhook to your server
6. Your server verifies the signature, marks the order paid, and fulfils

---

## Tokenized Cards

After a successful checkout, Nomba returns a card token representing the customer's card. You can charge that token later — for subscriptions, top-ups, or one-click re-orders — without the customer re-entering details. Tokens are scoped to your merchant.

| Endpoint | Description |
|---|---|
| `POST /tokenized-card/charge` | Charge a previously saved card token |
| `GET /tokenized-card/list` | List saved tokens for a customer |
| `DELETE /tokenized-card/{tokenId}` | Revoke a stored card token |

```python
nomba.post("/tokenized-card/charge", json={
    "amount": 500000,
    "currency": "NGN",
    "cardId": "tok_5fa12b...",
    "customerId": "cus_8821",
    "merchantTxRef": f"sub_2026_03_{customer_id}",
})
```

> **Subscriptions are your job.** Nomba does not run the schedule — you do. Store the token, run a cron, and charge on your billing cycle. Always send a unique `merchantTxRef` per attempt to make retries idempotent.

---

## Virtual Accounts

Virtual accounts are dedicated NUBAN accounts you can issue to any customer or invoice. When the customer transfers to that NUBAN from any Nigerian bank, you receive a webhook with the amount, sender, and your reference. Ideal for invoicing, escrow, and bank-transfer checkout flows.

| Endpoint | Description |
|---|---|
| `POST /accounts/virtual` | Create a permanent or one-time virtual account |
| `GET /accounts/virtual/{accountId}` | Fetch virtual account details and balance |

> **Handle over- and under-payment.** Even when you set an expected amount, the bank rails will accept any value. Compare `amountReceived` to `amountExpected` in your webhook handler — refund overpayments and surface short-payments to the customer.

---

## Webhooks

Webhooks are how Nomba notifies your server that something happened — a payment succeeded, a virtual account was funded, a transfer completed. Every webhook is signed with HMAC-SHA256 using your webhook secret. **Always verify the signature before trusting the payload.**

```python
import hmac, hashlib, os
from flask import request, abort

@app.post("/webhooks/nomba")
def nomba_webhook():
    body = request.get_data()
    signature = request.headers.get("nomba-signature")
    expected = hmac.new(
        os.environ["NOMBA_WEBHOOK_SECRET"].encode(),
        body, hashlib.sha256
    ).hexdigest()
    if signature != expected:
        abort(401)
    event = request.get_json()
    # Idempotency: ignore if we have already processed event["requestId"]
    return "", 200
```

> **Webhooks may fire twice.** Network retries can deliver the same event multiple times. Store `event.requestId` in a unique index and reject duplicates — never apply a balance change twice.

### Common Event Types

| Event | Fires when |
|---|---|
| `payment_success` | A checkout or token charge completes |
| `virtual_account.funded` | A NUBAN you issued receives a transfer |
| `transfer.success` | An outbound transfer settles to the recipient |
| `transfer.failed` | An outbound transfer is reversed |
| `mandate.debit_success` | A direct debit attempt clears |

---

## Transfers

Transfers move money out of your Nomba balance to any Nigerian bank account. Use them for payouts, refunds, and treasury operations. Every transfer requires a verified recipient and a unique `merchantTxRef`.

| Endpoint | Description |
|---|---|
| `POST /transfers/bank/lookup` | Resolve an account number to a name |
| `POST /transfers/bank` | Initiate a bank transfer |
| `GET /transfers/{merchantTxRef}` | Check transfer status |

```python
from uuid import uuid4

lookup = nomba.post("/transfers/bank/lookup", json={
    "bankCode": "044",
    "accountNumber": "0123456789",
})
nomba.post("/transfers/bank", json={
    "amount": 1500000,
    "bankCode": "044",
    "accountNumber": "0123456789",
    "accountName": lookup["data"]["accountName"],
    "senderName": "Acme Ltd",
    "narration": "Payout — March 2026",
    "merchantTxRef": f"payout_{uuid4()}",
})
```

> **Always lookup before transfer.** Sending to a wrong NUBAN can be irreversible. Display the resolved `accountName` to the user for confirmation before initiating the transfer.

---

## Mandates (Direct Debit)

A mandate is the customer's standing authorisation to debit their bank account on a recurring or on-demand basis. Use mandates for lending, BNPL, or any service that needs to pull funds without the customer initiating each charge. Mandates require explicit customer consent via OTP or in-app approval.

| Endpoint | Description |
|---|---|
| `POST /mandates/create` | Create a mandate — returns a consent URL |
| `POST /mandates/{mandateId}/debit` | Debit a previously approved mandate |
| `DELETE /mandates/{mandateId}` | Cancel an active mandate |

```python
mandate = nomba.post("/mandates/create", json={
    "customerId": "cus_8821",
    "maxAmount": 5000000,
    "frequency": "monthly",
    "startDate": "2026-04-01",
    "endDate": "2027-04-01",
})
# redirect customer to mandate["data"]["consentUrl"]
```

> **Respect the ceiling.** Attempting to debit more than `maxAmount` will fail. If your billing exceeds the ceiling, create a new mandate — do not split debits to bypass it.

---

## Reconciliation

Reconciliation is the discipline of matching what your app thinks happened against what Nomba records. Pull the transactions endpoint nightly, diff against your local ledger, and alert on any drift.

| Endpoint | Description |
|---|---|
| `GET /transactions` | List transactions (filters: `dateFrom`, `dateTo`, `status`, `type`) |
| `GET /transactions/{merchantTxRef}` | Look up a single transaction by your reference |

```python
data = nomba.get("/transactions", params={
    "dateFrom": "2026-03-01",
    "dateTo": "2026-03-31",
    "status": "success",
})["data"]

for tx in data["transactions"]:
    local = db.payments.find_one({"ref": tx["merchantTxRef"]})
    if not local:
        alert_ops("Orphan transaction on Nomba", tx)
    elif local["amount"] != tx["amount"]:
        alert_ops("Amount drift", {"local": local, "tx": tx})
```

> **Reconcile by reference, not by ID.** Your `merchantTxRef` is the source of truth. Use it to join Nomba's view with yours — Nomba's internal IDs may rotate during retries.

---

## Hackathon Track Guide

| Track | Primary APIs | Bonus polish |
|---|---|---|
| Marketplace / multi-vendor | Sub-accounts, Transfers, Webhooks | Reconciliation dashboard |
| Subscription product | Checkout, Tokenized Cards, Mandates | Retry strategy, dunning emails |
| Treasury / payouts | Transfers, Virtual Accounts, Transactions | Idempotency, audit log |
| Bank-transfer checkout | Virtual Accounts, Webhooks | Real-time UI updates |
| BNPL / lending | Mandates, Direct Debits, Transactions | Mandate lifecycle UI |

> **Pick depth over breadth.** A judge would rather see one API used flawlessly with proper webhook handling and reconciliation than five APIs glued together.

---

## Pre-submission Checklist

### Security
- [ ] `clientSecret` and `webhookSecret` loaded from environment variables — not in source
- [ ] All webhook handlers verify the `nomba-signature` HMAC
- [ ] Every external write keyed on a unique `merchantTxRef`

### Correctness
- [ ] All amounts converted to kobo before sending
- [ ] Recipient name verified via `/transfers/bank/lookup` before transfers
- [ ] Webhook handler is idempotent against duplicate `requestId` values
- [ ] Over- and under-payment branches handled for virtual accounts

### Operations
- [ ] Nightly reconciliation job comparing `/transactions` to your ledger
- [ ] Structured logging on every Nomba call with `merchantTxRef` tagged
- [ ] Health-check endpoint returning green status
