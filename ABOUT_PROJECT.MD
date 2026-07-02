# FillPot — Project Summary

---

## What Is FillPot?

FillPot is a web-based group contribution platform that eliminates the manual, chaotic process of collecting money from a group. Instead of posting a bank account number in a WhatsApp group and chasing people for screenshots, an organiser creates a pot, shares a link, and the platform handles everything automatically. Every contributor gets a dedicated virtual account, payments are attributed instantly, and a live public feed shows who has contributed and how much.

The name FillPot is internationally friendly, self-explanatory, and communicates the core mechanic — a pot that people fill together.

---

## The Problem It Solves

Group money collection in Nigeria today runs on WhatsApp messages, manual bank transfers, and receipt screenshots. Organisers spend hours chasing payments and updating spreadsheets. Contributors have no visibility into how much has been raised or who else has paid, which removes the social accountability that drives participation. Disputes arise over unacknowledged transfers and there is no single source of truth for who has paid what.

FillPot replaces this entirely with automatic payment attribution, real-time transparency, and a clean withdrawal experience for the organiser.

---

## Hackathon Track

**Primary track: Virtual Accounts as Infrastructure**

FillPot is a direct implementation of this track. Nomba explicitly listed "Ajo or esusu contribution tracking" as an example build under this category. Every contributor and pledger receives a dedicated Nomba virtual account, meaning every inbound transfer reconciles automatically to the correct person without any manual matching. The platform is judged on reconciliation logic quality, underpayment and overpayment handling, and customer-level reporting clarity — all of which are core to FillPot's design.

**Secondary track: Build Track (Merchant-Ready Experience)**

The organiser is effectively a merchant collecting money from a crowd. FillPot is a product anyone can use today without touching any code.

---

## How It Works

### For the Organiser
1. Signs up and creates a pot — giving it a name, description, target amount, and deadline
2. Chooses the pot type — Contribution Pot or Pledge Pot
3. Shares the unique invite link anywhere — WhatsApp, Twitter, email
4. Monitors the live dashboard showing who has paid, how much, and any outstanding balances
5. Withdraws the collected funds to their bank account when ready

### For the Contributor
1. Opens the invite link — no account required
2. Fills a simple form: full name, email, intended amount, and toggles for anonymous mode and group notifications
3. Receives a dedicated virtual account number to transfer to
4. Makes the bank transfer from any banking app
5. Their name appears on the live public feed automatically the moment the transfer lands
6. Receives an email receipt confirming their contribution

---

## Pot Types

### Contribution Pot
An open collection where contributors give any amount they choose. Suited for weddings, birthdays, burials, class trips, and fundraisers. Every contributor gets their own dedicated virtual account. Any transfer to that account is automatically attributed to them regardless of amount.

### Pledge Pot
A structured collection where contributors commit to a total amount and pay it in installments over time. Suited for long-term projects like church land purchases, community infrastructure, and cooperative savings. Each pledger gets a dedicated virtual account. Every transfer to that account accumulates against their pledge total automatically. When the total paid equals the total pledged, the pledge is marked complete.

---

## Agreed Features

### Pot Management
- Organiser creates a pot with name, description, occasion type, target amount, and deadline
- Two pot types: Contribution Pot and Pledge Pot
- Each pot gets a unique shareable invite link with a short slug
- Organiser can run multiple pots simultaneously
- Pot automatically closes when the deadline passes
- Organiser can view all past pots and their final totals

### Contribution Flow
- Contributor opens the invite link — no login or app download required
- Fills a form: full name, email, intended amount
- Receives a dedicated Nomba virtual account number unique to them
- Transfers money from their banking app to that account number
- Payment is automatically attributed to them the moment Nomba fires a webhook
- Name and amount appear on the live public feed instantly

### Pledge Flow
- Pledger commits to a total amount they will pay over time
- Receives a dedicated virtual account for all their installment payments
- Each transfer to their account accumulates against their pledge balance
- Pledge dashboard shows total pledged, total paid, remaining balance, and full payment history
- Pledge is marked complete when total paid meets or exceeds the committed amount

### Payment Reconciliation
- **Exact payment** — amount matches intended amount, contribution confirmed immediately
- **Underpayment** — amount is less than intended, recorded as partial, contributor notified of outstanding balance, virtual account stays active for top-up payments
- **Overpayment** — full amount credited, flagged for organiser review, contributor and organiser both notified of the excess
- **Top-up** — if a contribution is partial, a subsequent transfer to the same virtual account accumulates and re-evaluates the status automatically

### Live Feed and Social Features
- Public pot page shows a real-time feed of confirmed contributions
- Feed updates live the moment a payment lands via Server-Sent Events — no page refresh needed
- Progress bar showing total collected vs target amount, updates in real time
- Leaderboard showing top contributors by amount
- Contributor count displayed on the pot page
- Anonymous contributions — contributor's entry shows as "Anonymous" on the public feed

### Group Notifications
- Contributors can toggle group notifications on or off when filling the contribution form
- When toggled on, they receive an email every time anyone contributes to the pot
- Notification includes the contributor's name, amount, and the new pot total
- Organiser always receives a notification for every contribution by default

### Email Notifications
- Contribution receipt sent to contributor on confirmation
- Underpayment alert with outstanding balance and instruction to transfer to the same account
- Overpayment alert to contributor and organiser with the excess amount flagged
- Pledge payment receipt showing running total and remaining balance
- Pledge reminder email for pledgers who have not paid in 7 days
- Pot closure summary email to organiser with final totals
- Withdrawal confirmation email to organiser

### Organiser Dashboard
- Overview of all pots with status, total collected, target, contributor count, and deadline
- Per-pot contribution list filterable by status: confirmed, partial, overpaid, pending
- Single contributor view showing their full payment history — every individual transfer with amount, type, and timestamp
- Flagged overpayments listed separately for organiser review
- Unresolved payments visible and actionable

### Withdrawal
- Organiser enters their bank account number and bank code
- Platform verifies the account name via Nomba's bank lookup API before proceeding
- Organiser confirms and the transfer is executed via Nomba's bank transfer API
- One withdrawal per pot — duplicate withdrawal attempts are blocked
- Withdrawal confirmation email sent on success

---

## Payment Infrastructure

FillPot is built entirely on Nomba's payment infrastructure.

| Feature | Nomba API |
|---|---|
| Create contributor virtual account | Virtual Account API — POST /v1/accounts/virtual |
| Receive payment notifications | Transfers Webhook |
| Verify organiser bank account | Bank Account Lookup API |
| Execute organiser withdrawal | Bank Transfer API |
| Fetch transaction history | Transactions API |
| Expire virtual accounts at pot closure | Virtual Account expiry endpoint |

**Webhook URL:** `https://fillpot-production.up.railway.app/api/v1/webhooks/nomba`

**Webhook signing key:** `NombaHackathon2026` — every incoming webhook is verified against the `nomba-signature` header before processing to confirm it genuinely came from Nomba.

---

## Background Jobs

- **Pot expiry job** — runs hourly, closes pots past their deadline, expires all associated virtual accounts, and sends the organiser a closure summary
- **Pledge reminder job** — runs daily at 9am, identifies pledgers who have not paid in 7 days and sends a reminder email with their remaining balance

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django (Python) |
| Database | PostgreSQL |
| Real-time | Server-Sent Events |
| Background jobs | Celery + Redis |
| Email | Django EmailMessage + Brevo SMTP |
| Nomba integration | Python requests library |
| Hosting | Railway |

---

## Out of Scope for Hackathon

- WhatsApp group bot integration (discussed and deferred — feasible post-hackathon using Baileys but risky during a hackathon due to potential number bans)
- Mobile app
- Escrow or fund locking
- SMS notifications
- Social login
- Platform admin dashboard
- Multi-currency support

---

## Demo Success Criteria

A successful hackathon demo shows the following end to end:

1. Organiser creates a contribution pot and a pledge pot
2. Invite link opens a working public pot page
3. Contributor fills the form and receives a dedicated virtual account number
4. Transfer is made and the contributor's name appears on the live feed automatically
5. Underpayment scenario demonstrated — partial status shown, top-up completes the contribution
6. Overpayment scenario demonstrated — flagged in organiser dashboard
7. Organiser dashboard shows full per-contributor payment history
8. Organiser successfully initiates and completes a withdrawal
9. Email receipt delivered to contributor's inbox in real time