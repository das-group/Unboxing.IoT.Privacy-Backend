import uuid
from dataclasses import dataclass

import bcrypt
import redis
from src.config import ORIGIN, REDIS_HOST, REDIS_PORT
from src.db_users import UserData, get_user_by_email, get_user_by_id
from src.errors import (
    AuthenticationFailedError,
    CredentialNotFoundError,
    UnknownAuthenticationFlowError,
    UserNotFoundError,
)
from webauthn import (
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers import base64url_to_bytes, options_to_json_dict
from webauthn.helpers.exceptions import InvalidAuthenticationResponse
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    PublicKeyCredentialRequestOptions,
    UserVerificationRequirement,
)

## --------------------- Redis Setup for Authentication Challenges --------------------- ##

LOGIN_CHALLENGES: redis.Redis = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=1,
)


def set_authentication_challenge(login_id: str, challenge: bytes):
    LOGIN_CHALLENGES.set(login_id, challenge, ex=120)  # 2 minute


def get_authentication_challenge(login_id: str) -> bytes:
    raw = LOGIN_CHALLENGES.get(login_id)

    return bytes(raw)


def delete_authentication_challenge(login_id: str):
    LOGIN_CHALLENGES.delete(login_id)


## --------------------- Authentication Flow --------------------- ##


async def authentication_start(service_id: str) -> dict:
    # Generate login options
    options: PublicKeyCredentialRequestOptions = generate_authentication_options(
        rp_id=service_id,
        allow_credentials=[],
        timeout=120000,  # 2 minutes
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    # Store challenge for verification later
    login_id = str(uuid.uuid4())
    set_authentication_challenge(
        login_id,
        options.challenge,
    )

    return {
        **options_to_json_dict(options),
        "login_id": login_id,
    }


@dataclass
class LoginVerifyRequest:
    login_id: str
    id: str
    rawId: str
    authenticatorData: str
    clientDataJSON: str
    signature: str
    type: str
    userHandle: str


async def authentication_finish(data: LoginVerifyRequest, service_id: str) -> UserData:
    # Retrieve login session
    challenge = get_authentication_challenge(data.login_id)
    if not challenge:
        raise UnknownAuthenticationFlowError()

    user_id = base64url_to_bytes(data.userHandle).decode("utf-8")

    # get user
    user = await get_user_by_id(user_id)
    if not user:
        delete_authentication_challenge(data.login_id)
        raise UserNotFoundError()

    # find matching credential
    credential = next((x for x in user.passkey_credentials if x.id == data.id), None)
    if credential is None:
        delete_authentication_challenge(data.login_id)
        raise CredentialNotFoundError()

    assert data.id == credential.id
    public_key = credential.public_key

    try:
        # Verify authentication response
        _verified_authentication = verify_authentication_response(
            credential=AuthenticationCredential(
                id=data.id,
                raw_id=base64url_to_bytes(data.rawId),
                response=AuthenticatorAssertionResponse(
                    client_data_json=base64url_to_bytes(data.clientDataJSON),
                    authenticator_data=base64url_to_bytes(data.authenticatorData),
                    signature=base64url_to_bytes(data.signature),
                    user_handle=(
                        base64url_to_bytes(data.userHandle) if data.userHandle else None
                    ),
                ),
            ),
            expected_challenge=challenge,
            expected_rp_id=service_id,
            expected_origin=ORIGIN,
            credential_public_key=public_key,
            credential_current_sign_count=0,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse:
        delete_authentication_challenge(data.login_id)
        raise AuthenticationFailedError()

    # assert verified_authentication.new_sign_count == 0

    delete_authentication_challenge(data.login_id)

    return user


async def authenticate_with_password(email: str, password: str) -> UserData:
    # get user
    user = await get_user_by_email(email)
    if not user:
        raise UserNotFoundError()

    if not user.password_credentials:
        raise CredentialNotFoundError()

    # verify password
    if not bcrypt.checkpw(
        password.encode("utf-8"),
        user.password_credentials.password_hash,
    ):
        raise AuthenticationFailedError()

    return user
