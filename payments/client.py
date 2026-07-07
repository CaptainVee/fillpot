import threading
from decimal import Decimal

import requests
import structlog
from django.conf import settings
from django.core.cache import cache

from .exceptions import NombaAPIError, NombaAuthError, NombaRateLimitError

log = structlog.get_logger(__name__)

_TOKEN_CACHE_KEY = "fillpot:nomba:access_token"
_TOKEN_TTL       = 3300  # 55 minutes (tokens last 60 min)
_token_lock      = threading.Lock()


def to_kobo(naira: Decimal) -> int:
    return int(naira * 100)


def from_kobo(kobo: int) -> Decimal:
    return Decimal(kobo) / 100


class NombaClient:
    """
    Thin wrapper around the Nomba REST API.

    Token lifecycle: cached via Django's cache framework (in-process memory by
    default) with a 55-min TTL. A process-local lock prevents concurrent
    threads in the same worker from all fetching a fresh token at once.
    On 401, the cached token is evicted and the request is retried once.
    """

    def __init__(self):
        self.base_url     = settings.NOMBA_BASE_URL.rstrip("/")
        self.account_id   = settings.NOMBA_CLIENT_ID
        self.client_id    = settings.NOMBA_CLIENT_ID
        self.client_secret = settings.NOMBA_CLIENT_SECRET
        self.account_id   = settings.NOMBA_ACCOUNT_ID

    # ── Token management ────────────────────────────────────────────────────

    def _fetch_token(self) -> str:
        """Call /auth/token/issue. Should only be called when the cache is cold."""
        resp = requests.post(
            f"{self.base_url}/auth/token/issue",
            headers={
                "Content-Type": "application/json",
                "accountId": self.account_id,
            },
            json={
                "grant_type": "client_credentials",
                "client_id":  self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            raise NombaAuthError(
                f"Token issuance failed: {resp.status_code}",
                status_code=resp.status_code,
                response_body=resp.text,
            )
        data = resp.json().get("data", {})
        token = data.get("access_token") or data.get("accessToken")
        if not token:
            raise NombaAuthError(f"No access_token in response: {resp.text}")
        return token

    def _get_token(self) -> str:
        cached = cache.get(_TOKEN_CACHE_KEY)
        if cached:
            return cached

        with _token_lock:
            # Another thread may have refreshed it while we waited for the lock
            cached = cache.get(_TOKEN_CACHE_KEY)
            if cached:
                return cached
            token = self._fetch_token()
            cache.set(_TOKEN_CACHE_KEY, token, timeout=_TOKEN_TTL)
            return token

    def _evict_token(self):
        cache.delete(_TOKEN_CACHE_KEY)

    # ── Base request ─────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, *, _retry_on_401=True, **kwargs) -> dict:
        token = self._get_token()
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {token}",
            "accountId":     self.account_id,
            "Content-Type":  "application/json",
        })

        url = f"{self.base_url}/{path.lstrip('/')}"
        log.info("nomba_request", method=method, path=path,
                 merchant_tx_ref=kwargs.get("json", {}).get("merchantTxRef"))

        resp = requests.request(method, url, headers=headers, timeout=10, **kwargs)

        log.info("nomba_response", method=method, path=path, status=resp.status_code)

        if resp.status_code == 401 and _retry_on_401:
            self._evict_token()
            return self._request(method, path, _retry_on_401=False, **kwargs)

        if resp.status_code == 429:
            raise NombaRateLimitError("Rate limited by Nomba", status_code=429, response_body=resp.text)

        if resp.status_code >= 500:
            raise NombaAPIError(
                f"Nomba server error {resp.status_code}",
                status_code=resp.status_code,
                response_body=resp.text,
            )

        body = resp.json()
        code = body.get("code", "")
        if resp.status_code >= 400 or (code and code != "00"):
            raise NombaAPIError(
                body.get("description", f"Nomba error {resp.status_code}"),
                status_code=resp.status_code,
                response_body=resp.text,
            )

        return body.get("data", body)

    # ── Public API methods ───────────────────────────────────────────────────

    def create_virtual_account(self, customer_name: str, email: str, customer_ref: str) -> dict:
        """
        Create a dedicated NUBAN for a contributor.

        Returns dict with at minimum:
          accountId, accountNumber, bankName
        """
        data = self._request("POST", "/accounts/virtual", json={
            "accountName":   customer_name[:100],
            "customerEmail": email,
            "accountRef":    customer_ref,
        })
        return data

    def lookup_bank_account(self, bank_code: str, account_number: str) -> dict:
        """Resolve account number to name. Returns dict with accountName."""
        return self._request("POST", "/transfers/bank/lookup", json={
            "bankCode":       bank_code,
            "accountNumber":  account_number,
        })

    def transfer(
        self,
        amount_naira: Decimal,
        bank_code: str,
        account_number: str,
        account_name: str,
        narration: str,
        merchant_tx_ref: str,
    ) -> dict:
        return self._request("POST", "/transfers/bank", json={
            "amount":          to_kobo(amount_naira),
            "bankCode":        bank_code,
            "accountNumber":   account_number,
            "accountName":     account_name,
            "senderName":      "FillPot",
            "narration":       narration,
            "merchantTxRef":   merchant_tx_ref,
        })

    def get_transactions(self, date_from: str, date_to: str, status: str = "SUCCESS", limit: int = 100) -> list:
        """
        Pull transaction list for nightly reconciliation. Dates: 'YYYY-MM-DD' (UTC day boundaries).
        Real endpoint per developer.nomba.com: GET /transactions/accounts/{subAccountId},
        dateFrom/dateTo/limit/cursor as query params, status/type/etc. as a JSON body on the GET.
        `status` is one of: NEW, PENDING_PAYMENT, PAYMENT_SUCCESSFUL, PAYMENT_FAILED,
        PENDING_BILLING, SUCCESS, REFUND. Pass None to skip the status filter.
        """
        params = {
            "dateFrom": f"{date_from}T00:00:00.000Z",
            "dateTo":   f"{date_to}T23:59:59.999Z",
            "limit":    limit,
        }
        body = {"status": status} if status else {}
        data = self._request(
            "GET",
            f"/transactions/accounts/{self.account_id}",
            params=params,
            json=body,
        )
        return data.get("results", data) if isinstance(data, dict) else data
