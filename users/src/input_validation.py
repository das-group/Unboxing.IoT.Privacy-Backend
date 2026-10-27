from src.errors import (
    MalformedEmailError,
    MalformedPasswordError,
    MalformedUsernameError,
)


def validate_password(password: str) -> bool:
    """Validate password strength."""
    if len(password) < 8:
        return False
    if not any(c.isupper() for c in password):
        return False
    if not any(c.islower() for c in password):
        return False
    if not any(c.isdigit() for c in password):
        return False
    if not any(c in "!@#$%^&*()-_=+[{]}\\|;:'\",<.>/?`~" for c in password):
        return False
    return True


def validate_username(username: str) -> bool:
    """Validate username format. 3-30 characters, alnum + ' ', '.', '_' """
    ALLOWED_SPECIAL_CHARS = {" ", ".", "_"}
    if not (3 <= len(username) <= 30):
        return False
    if not all(c.isalnum() or c in ALLOWED_SPECIAL_CHARS for c in username):
        return False
    if not any(c.isalnum() for c in username):
        return False
    # No leading or trailing space, dot or underscore
    if username[0] in ALLOWED_SPECIAL_CHARS or username[-1] in ALLOWED_SPECIAL_CHARS:
        return False
    # No two special characters in a row (e.g. "a..b", "a  b", "a._b")
    for a, b in zip(username, username[1:]):
        if a in ALLOWED_SPECIAL_CHARS and b in ALLOWED_SPECIAL_CHARS:
            return False
    return True

def validate_email(email: str) -> bool:
    """Validate email format."""
    import re

    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(email_regex, email) is not None


def validate_user_registration(username: str, email: str, password: str | None) -> None:
    """Validate user registration data."""

    if not validate_username(username):
        raise MalformedUsernameError()
    if not validate_email(email):
        raise MalformedEmailError()
    if password and not validate_password(password):
        raise MalformedPasswordError()
