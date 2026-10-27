from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from src.authentication import LoginVerifyRequest as AuthLoginVerifyRequest
from src.authentication import (
    authenticate_with_password,
    authentication_finish,
    authentication_start,
)
from src.config import (
    MONGO_DB,
    MONGO_HOST,
    MONGO_PASS,
    MONGO_PORT,
    MONGO_USER,
    ORIGIN,
    RP_ID,
    RP_NAME,
    SESSION_DURATION_DAYS,
)
from src.db_users import (
    UserData,
    delete_passkey,
    delete_user,
    get_all_users,
    get_user_by_id,
    update_user,
    username_update,
    get_settings_for_user,
    set_settings_for_user,
)
from src.errors import InvalidSessionError, NoPermissionError
from src.input_validation import validate_user_registration
from src.registration import (
    VerificationData,
    register_finish,
    register_passkey_finish,
    register_passkey_start,
    register_start,
    register_with_password,
)
from src.sessions import (
    SessionData,
    create_session,
    delete_session,
    get_user_id_by_session_token,
    verify_session,
)
from typing_extensions import Annotated

router = APIRouter()

WHITELIST = ["localhost", "iot-privacy.info", "platform.iot-privacy.info"]


def _get_service_id(host: str | None) -> str:
    if host is None:
        return RP_ID

    if host in WHITELIST:
        return host

    assert False, "Host not in whitelist"


####

# Happy little helpers, should be fixed for later


URI: str = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}"
CLIENT: AsyncMongoClient = AsyncMongoClient(URI)

USERS_DB: AsyncDatabase = CLIENT.get_database(MONGO_DB)

#

bearer_scheme = HTTPBearer(auto_error=False)


async def get_user_id_by_session(
    token: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: str | None = Cookie(default=None, alias="session"),
):
    auth_token = None
    if token:
        auth_token = token.credentials
    else:
        auth_token = session

    if auth_token is None:
        return None

    session_check = get_user_id_by_session_token(
        auth_token.replace('"', "").split(":")[1]
    )
    if session_check is None:
        return None

    return session_check


# Returns UserData object if permission exists
def require_permission(permission: str):
    async def dependency(
        token: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        session: str | None = Cookie(default=None, alias="session"),
    ):
        auth_token = None
        if token:
            auth_token = token.credentials
        else:
            auth_token = session

        if auth_token is None:
            return None

        user_id = get_user_id_by_session_token(
            auth_token.replace('"', "").split(":")[1]
        )
        if user_id is None:
            raise InvalidSessionError()

        # Fetch user for session
        user: UserData = await get_user_by_id(user_id)

        if not user:
            raise InvalidSessionError()

        # Hardcoded admin '*' permission to grant any permission
        if "*" in user.permissions:
            return user

        # Check if user has permission
        if permission not in user.permissions:
            raise NoPermissionError()
        return user

    return dependency


####

## ----------------------- Registration endpoints ----------------------- ##


class RegisterOptionsRequest(BaseModel):
    username: str
    email: str


@router.post("/register/webauthn/options", tags=["webauthn-registration"])
async def register_options(
    data: RegisterOptionsRequest,
    host: Annotated[str | None, Header(alias="X-RP-Host")] = None,
):
    username: str = data.username
    email: str = data.email or ""

    validate_user_registration(username, email, None)

    out = await register_start(
        username=username,
        email=email,
        rp_name=RP_NAME,
        service_id=_get_service_id(host),
    )

    return JSONResponse(content=out, status_code=200)


class RegisterVerifyRequest(BaseModel):
    id: str
    rawId: str
    client_data_json: str
    attestation_object: str
    type: str
    user_id: str


@router.post("/register/webauthn/verify", tags=["webauthn-registration"])
async def register_verify(
    data: RegisterVerifyRequest,
    host: Annotated[str | None, Header(alias="X-RP-Host")] = None,
):
    verification_data = VerificationData(
        user_id=data.user_id,
        credential_id=data.id,
        credential_raw_id=data.rawId,
        client_data_json=data.client_data_json,
        attestation_object=data.attestation_object,
        service_id=_get_service_id(host),
        origin=ORIGIN,
    )

    out = await register_finish(verification_data)

    return JSONResponse(content=out, status_code=200)


class RegisterPasswordRequest(BaseModel):
    username: str
    email: str
    password: str


@router.post("/register/passwd", tags=["password-registration"])
async def register_password(data: RegisterPasswordRequest):
    validate_user_registration(data.username, data.email, data.password)

    out = await register_with_password(
        username=data.username,
        email=data.email,
        password=data.password,
    )

    return JSONResponse(content=out, status_code=200)


## ----------------------- Login endpoints ----------------------- ##


@router.post("/login/webauthn/options", tags=["webauthn-authentication"])
async def login_options(
    host: Annotated[str | None, Header(alias="X-RP-Host")] = None,
):
    out = await authentication_start(service_id=_get_service_id(host))

    return JSONResponse(content=out, status_code=200)


class LoginVerifyRequest(BaseModel):
    login_id: str
    id: str
    rawId: str
    authenticatorData: str
    clientDataJSON: str
    signature: str
    userHandle: str | None = None
    type: str


class UserDataResponse(BaseModel):
    username: str
    id: str
    email: str
    role_admin: bool
    role_contributor: bool
    permissions: list


class AuthDataResponse(BaseModel):
    token: str
    expires: datetime


class LoginResponse(BaseModel):
    user: UserDataResponse
    auth: AuthDataResponse


async def finish_login(user: UserData, response: Response) -> LoginResponse:
    session = create_session(user._id)
    expires = datetime.now() + timedelta(days=SESSION_DURATION_DAYS)

    print("Sesesion created:", session.to_str())

    response.set_cookie(
        key="session",
        value=session.to_str(),
        httponly=True,
        expires=expires.timestamp(),
        # TOOD: secure=True,
    )

    return LoginResponse(
        user=UserDataResponse(
            username=user.username,
            id=user._id,
            email=user.email,
            role_admin=user.role_admin,
            role_contributor=user.role_contributor,
            permissions=user.permissions,
        ),
        auth=AuthDataResponse(
            token=session.to_str(),
            expires=expires,
        ),
    )


@router.post("/login/webauthn/verify", tags=["webauthn-authentication"])
async def login_verify(
    data: LoginVerifyRequest,
    response: Response,
    host: Annotated[str | None, Header(alias="X-RP-Host")] = None,
) -> LoginResponse:
    user = await authentication_finish(
        AuthLoginVerifyRequest(
            login_id=data.login_id,
            id=data.id,
            rawId=data.rawId,
            authenticatorData=data.authenticatorData,
            clientDataJSON=data.clientDataJSON,
            signature=data.signature,
            type=data.type,
            userHandle=data.userHandle or "",
        ),
        service_id=_get_service_id(host),
    )

    return await finish_login(user, response)


class LoginPasswordRequest(BaseModel):
    email: str
    password: str


@router.post("/login/passwd", tags=["password-authentication"])
async def login_password(
    data: LoginPasswordRequest,
    response: Response,
) -> LoginResponse:
    user = await authenticate_with_password(
        email=data.email,
        password=data.password,
    )

    return await finish_login(user, response)


## ----------------------- Session endpoint ----------------------- ##


class SessionInfoResponse(BaseModel):
    expires_at: str | None = None
    username: str | None = None
    email: str | None = None
    id: str | None = None
    admin: bool | None = None
    contributor: bool | None = None
    permissions: list[str] | None = None


@router.get(
    "/session/info",
    tags=["session"],
    responses={401: {"description": "INVALID_SESSION"}},
)
async def validate_session(token: str) -> SessionInfoResponse:
    session = SessionData.from_str(token)

    session_check = verify_session(session)

    if session_check is None:
        raise InvalidSessionError()

    user: UserData = await get_user_by_id(session.user_id)

    return SessionInfoResponse(
        expires_at=session_check.isoformat(),
        username=user.username,
        email=user.email,
        id=user._id,
        admin=user.role_admin,
        contributor=user.role_contributor,
        permissions=user.permissions,
    )


@router.delete("/session/revoke", tags=["session"])
async def revoke_session(token: str):
    existed = delete_session(SessionData.from_str(token))

    if not existed:
        return JSONResponse(
            status_code=204,
            content={"status": "SESSION_NOT_FOUND"},
        )

    return JSONResponse(status_code=200, content={"status": "SESSION_REVOKED"})


## ----------------------- Profile endpoints ----------------------- ##


class UsernameUpdateRequest(BaseModel):
    new_username: str


@router.post("/user/update/username", tags=["Profile"])
async def update_username(
    data: UsernameUpdateRequest, user_id: str | None = Depends(get_user_id_by_session)
):
    modified = await username_update(user_id, data.new_username)

    if modified:
        return JSONResponse(
            content={"status": "USERNAME_UPDATED", "new_username": data.new_username},
            status_code=200,
        )
    else:
        return JSONResponse(
            content={"status": "USERNAME_NOT_MODIFIED"}, status_code=200
        )


# Passkey management
# Get passkeys
@router.get("/user/passkeys", tags=["Account"])
async def get_passkeys(
    request: Request, user_id: str | None = Depends(get_user_id_by_session)
):
    if user_id is None:
        raise InvalidSessionError()

    user: UserData = await get_user_by_id(user_id)

    passkey_list = [
        {
            "id": cred.id,
            "name": cred.name,
            "created_at": cred.creation_date.isoformat(timespec="seconds"),
        }
        for cred in user.passkey_credentials
    ]

    return JSONResponse(content=passkey_list, status_code=200)


# Add Passkey


# Analog zu /register/webauthn/options
@router.post("/user/passkeys/new/start", tags=["Account"])
async def start_passkey_reg(
    request: Request,
    user_id: str | None = Depends(get_user_id_by_session),
    host: Annotated[str | None, Header(alias="X-RP-Host")] = None,
):
    if user_id is None:
        raise InvalidSessionError()

    user: UserData = await get_user_by_id(user_id)

    out = await register_passkey_start(
        user._id, user.username, user.email, RP_NAME, _get_service_id(host)
    )

    return JSONResponse(content=out, status_code=200)


# /register/webauthn/verify
@router.post("/user/passkeys/new/verify", tags=["webauthn-registration"])
async def register_verify(
    data: RegisterVerifyRequest,
    host: Annotated[str | None, Header(alias="X-RP-Host")] = None,
    user_id: str | None = Depends(get_user_id_by_session),
):
    verification_data = VerificationData(
        user_id=data.user_id,
        credential_id=data.id,
        credential_raw_id=data.rawId,
        client_data_json=data.client_data_json,
        attestation_object=data.attestation_object,
        service_id=_get_service_id(host),
        origin=ORIGIN,
    )

    out = await register_passkey_finish(verification_data)

    return JSONResponse(content=out, status_code=200)


@router.delete("/user/passkeys/{passkey_id}")
async def register_verify(
    passkey_id: str,
    host: Annotated[str | None, Header(alias="X-RP-Host")] = None,
    user_id: str | None = Depends(get_user_id_by_session),
):
    print("Delete passkey " + passkey_id)

    out = await delete_passkey(user_id, passkey_id)

    return {"status": out}

# Delete account

@router.delete("/account", tags=["Profile"])
async def update_username(
    user_id: str | None = Depends(get_user_id_by_session)
):
    print("Account deletion requested")

    result = await delete_user(user_id)

    return JSONResponse(content={"success": result}, status_code=200)


# User management / Moderation


@router.get("/management/users", tags=["Admin"])
async def get_users(
    request: Request,
    user: UserData | None = Depends(require_permission("manage_users")),
):
    user_list = await get_all_users()

    return JSONResponse(content=user_list, status_code=200)


class UpdateUserRequest(BaseModel):
    username: str | None
    email: str | None
    permissions: list | None


@router.post("/management/user/{user_id}", tags=["Admin"])
async def update_user_handler(
    request: Request,
    data: UpdateUserRequest,
    user_id: str,
    user: UserData | None = Depends(require_permission("manage_users")),
):
    result = await update_user(user_id, data.username, data.email, data.permissions)

    return JSONResponse(content={"success": result}, status_code=200)


@router.delete("/management/user/{user_id}", tags=["Admin"])
async def delete_user_handler(
    request: Request,
    user_id: str,
    user: UserData | None = Depends(require_permission("manage_users")),
):
    result = await delete_user(user_id)

    return JSONResponse(content={"success": result}, status_code=200)


@router.get("/user/{user_id}", tags=["User"])
async def fetch_user_info(
    request: Request,
    user_id: str
):
    
    # TODO: Rate limit when user id not found

    user: UserData = await get_user_by_id(user_id)

    return JSONResponse(content={"username": user.username}, status_code=200)

@router.get("/user/{user_id}/settings", tags=["User"])
async def dump_settings(user_id: str):
    return JSONResponse(content=await get_settings_for_user(user_id), status_code=200)

@router.post("/user/{user_id}/settings", tags=["User"])
async def load_settings(settings_dump: dict, user_id: str):
    if await set_settings_for_user(user_id, settings_dump):
        return JSONResponse(content={"status": "success"}, status_code=202)

    return JSONResponse(content={"status": "error"}, status_code=500)
