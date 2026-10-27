from dataclasses import dataclass


@dataclass
class PublicError(Exception):
    """Base class for public errors presented to users."""

    error_code: str
    http_status: int
    message: str


class LoginRequiredError(PublicError):
    """Raised when authentication is required but not provided."""

    def __init__(self):
        super().__init__(
            error_code="LOGIN_REQUIRED",
            http_status=401,
            message="Authentication is required to access this resource.",
        )


class InsufficientPermissionsError(PublicError):
    """Raised when the user does not have sufficient permissions."""

    def __init__(self):
        super().__init__(
            error_code="INSUFFICIENT_PERMISSIONS",
            http_status=403,
            message="You do not have sufficient permissions to access this resource.",
        )


class InvalidInputError(PublicError):
    """Raised when the input provided by the user is invalid."""

    def __init__(self, message: str):
        super().__init__(
            error_code="INVALID_INPUT",
            http_status=400,
            message=message,
        )
