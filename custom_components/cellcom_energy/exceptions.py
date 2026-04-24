"""Custom exceptions for the Cellcom Energy integration."""


class CellcomError(Exception):
    """Base exception for all Cellcom Energy errors."""


class CellcomConnectionError(CellcomError):
    """Raised when the integration cannot reach the Cellcom API."""


class CellcomAuthError(CellcomError):
    """Raised when authentication fails (bad credentials or expired token)."""


class CellcomOTPError(CellcomAuthError):
    """Raised when the OTP code is invalid, expired, or already used."""


class CellcomIDError(CellcomAuthError):
    """Raised when the ID number does not match the account."""


class CellcomAPIError(CellcomError):
    """Raised when the API returns a non-zero ReturnCode."""

    def __init__(self, return_code: int, message: str) -> None:
        """Initialise with the API error code and message."""
        super().__init__(message)
        self.return_code = return_code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.return_code}] {self.message}"


class CellcomTokenExpiredError(CellcomAuthError):
    """Raised when both the access token and refresh token have expired.

    This should trigger a full reauth flow via ConfigEntryAuthFailed.
    """
