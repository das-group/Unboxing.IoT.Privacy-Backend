from dataclasses import dataclass
from datetime import datetime

import httpx
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.config import USER_SERVICE
from src.errors import (
    InsufficientPermissionsError,
    InvalidInputError,
    LoginRequiredError,
)


@dataclass
class SessionInfo:
    user_id: str
    username: str
    email: str
    admin: bool
    contributor: bool
    permissions: list[str]
    expires_at: datetime


bearer_scheme = HTTPBearer(auto_error=False)


async def get_user_by_token(
    token: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: str | None = Cookie(default=None, alias="session"),
) -> SessionInfo:
    auth_token = None
    if token:
        auth_token = token.credentials
    else:
        auth_token = session

    if auth_token is None:
        raise LoginRequiredError()

    extracted_session_token = auth_token.replace('"', "")

    # Get user id by session token
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{USER_SERVICE}/session/info",
            params={"token": extracted_session_token},
        )

    if resp.status_code >= 500:
        raise Exception("User service error")

    if resp.status_code == 400:
        raise InvalidInputError("Malformed session token.")

    if resp.status_code == 401:
        raise LoginRequiredError()

    data = resp.json()

    info = SessionInfo(
        user_id=data["id"],
        username=data["username"],
        email=data["email"],
        admin=data["admin"],
        contributor=data["contributor"],
        permissions=data["permissions"],
        expires_at=datetime.fromisoformat(data["expires_at"]),
    )

    return info

# get_user_by_token, Optional auth variant
async def get_user_by_token_optional(
    token: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: str | None = Cookie(default=None, alias="session"),
) -> SessionInfo | None:
    auth_token = token.credentials if token else session

    if auth_token is None:
        return None

    try:
        extracted_session_token = auth_token.replace('"', "")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://{USER_SERVICE}/session/info",
                params={"token": extracted_session_token},
            )

        if resp.status_code >= 500:
            raise Exception("User service error")

        if resp.status_code in (400, 401):
            return None  

        data = resp.json()
        return SessionInfo(
            user_id=data["id"],
            username=data["username"],
            email=data["email"],
            admin=data["admin"],
            contributor=data["contributor"],
            permissions=data["permissions"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
    except Exception:
        return None

# Returns UserData object if permission exists
def require_permission(permission: str):
    async def dependency(
        user_data: SessionInfo = Depends(get_user_by_token),
    ) -> SessionInfo:
        # Hardcoded admin '*' permission to grant any permission
        if "*" in user_data.permissions:
            return user_data

        # Check if user has permission
        if permission not in user_data.permissions:
            raise InsufficientPermissionsError()
        return user_data

    return dependency
