from dataclasses import dataclass


@dataclass
class PublicError(Exception):
    """Base class for public errors presented to users."""

    error_code: str
    http_status: int
    message: str


class UnknownRegistrationFlowError(PublicError):
    """Raised when a registration flow is unknown or invalid."""

    def __init__(self):
        super().__init__(
            error_code="UNKNOWN_REGISTRATION_FLOW",
            http_status=400,
            message="Unknown or invalid registration flow.",
        )


class UnknownAuthenticationFlowError(PublicError):
    """Raised when an authentication flow is unknown or invalid."""

    def __init__(self):
        super().__init__(
            error_code="UNKNOWN_AUTHENTICATION_FLOW",
            http_status=400,
            message="Unknown or invalid authentication flow.",
        )


class EmailAlreadyExistsError(PublicError):
    """Raised when an email already exists."""

    def __init__(self):
        super().__init__(
            error_code="EMAIL_ALREADY_EXISTS",
            http_status=409,
            message="Email already exists.",
        )


class UsernameAlreadyExistsError(PublicError):
    """Raised when a username already exists."""

    def __init__(self):
        super().__init__(
            error_code="USERNAME_ALREADY_EXISTS",
            http_status=409,
            message="Username already exists.",
        )


class UserNotFoundError(PublicError):
    """Raised when a user is not found."""

    def __init__(self):
        super().__init__(
            error_code="USER_NOT_FOUND",
            http_status=404,
            message="User not found.",
        )


class MalformedCredentialError(PublicError):
    """Raised when a credential is malformed."""

    def __init__(self):
        super().__init__(
            error_code="MALFORMED_CREDENTIAL",
            http_status=400,
            message="Malformed credential.",
        )


class InvalidSessionError(PublicError):
    """Raised when a session is invalid."""

    def __init__(self):
        super().__init__(
            error_code="INVALID_SESSION",
            http_status=401,
            message="Invalid session.",
        )


class CredentialNotFoundError(PublicError):
    """Raised when a credential is not found."""

    def __init__(self):
        super().__init__(
            error_code="CREDENTIAL_NOT_FOUND",
            http_status=404,
            message="Credential not found.",
        )


class AuthenticationFailedError(PublicError):
    """Raised when authentication fails."""

    def __init__(self):
        super().__init__(
            error_code="AUTHENTICATION_FAILED",
            http_status=401,
            message="Authentication failed.",
        )


class MalformedEmailError(PublicError):
    """Raised when an email is malformed."""

    def __init__(self):
        super().__init__(
            error_code="MALFORMED_EMAIL",
            http_status=400,
            message="Malformed email address.",
        )


class MalformedUsernameError(PublicError):
    """Raised when a username is malformed."""

    def __init__(self):
        super().__init__(
            error_code="MALFORMED_USERNAME",
            http_status=400,
            message="Malformed username.",
        )


class MalformedPasswordError(PublicError):
    """Raised when a password is malformed."""

    def __init__(self):
        super().__init__(
            error_code="MALFORMED_PASSWORD",
            http_status=400,
            message="Malformed password.",
        )


class NoPermissionError(PublicError):
    """Raised when a user has no permission for a specific endpoint."""

    def __init__(self):
        super().__init__(
            error_code="NO_PERMISSION",
            http_status=403,
            message="No permission",
        )
