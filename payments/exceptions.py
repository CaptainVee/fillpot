class NombaAPIError(Exception):
    """Non-2xx response from the Nomba API."""
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class NombaAuthError(NombaAPIError):
    """Token issuance or 401 from Nomba."""


class NombaRateLimitError(NombaAPIError):
    """429 from Nomba."""
