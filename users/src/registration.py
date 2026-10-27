import uuid
from dataclasses import dataclass

import bcrypt
import redis
from src.config import DEFAULT_USER_PERMISSIONS, REDIS_HOST, REDIS_PORT
from src.db_users import (
    PasskeyCredential,
    PasswordCredential,
    UserData,
    add_passkey,
    insert_user,
)
from src.errors import UnknownRegistrationFlowError
from webauthn import (
    generate_registration_options,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, options_to_json_dict
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorAttestationResponse,
    RegistrationCredential,
)

## --------------------- Redis Setup for Registration Challenges --------------------- ##

REGISTRATION_CHALLENGES: redis.Redis = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
)
###
PASSKEY_CHALLENGES: redis.Redis = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=10,
)


@dataclass
class PasskeyChallenge:
    challenge: bytes
    user_id: str


def store_passkey_challenge(user_id: str, data: PasskeyChallenge):
    store = {"challenge": data.challenge, "user_id": data.user_id}
    PASSKEY_CHALLENGES.hset(user_id, mapping=store)
    PASSKEY_CHALLENGES.expire(user_id, 120)  # 2 minutes


def get_passkey_challenge(user_id: str) -> PasskeyChallenge:
    raw: dict[bytes, bytes] = PASSKEY_CHALLENGES.hgetall(user_id)
    raw: dict[str, bytes] = {k.decode("utf-8"): v for k, v in raw.items()}

    return PasskeyChallenge(
        challenge=raw["challenge"], user_id=raw["user_id"].decode("utf-8")
    )


def delete_passkey_challenge(user_id: str):
    REGISTRATION_CHALLENGES.delete(user_id)


###


@dataclass
class RegistrationChallenge:
    challenge: bytes
    user_id: str
    username: str
    email: str


def store_registration_challenge(user_id: str, data: RegistrationChallenge):
    store = {
        "challenge": data.challenge,
        "user_id": data.user_id,
        "username": data.username,
        "email": data.email,
    }
    REGISTRATION_CHALLENGES.hset(user_id, mapping=store)
    REGISTRATION_CHALLENGES.expire(user_id, 120)  # 2 minutes


def get_registration_challenge(user_id: str) -> RegistrationChallenge:
    raw: dict[bytes, bytes] = REGISTRATION_CHALLENGES.hgetall(user_id)
    raw: dict[str, bytes] = {k.decode("utf-8"): v for k, v in raw.items()}

    return RegistrationChallenge(
        challenge=raw["challenge"],
        user_id=raw["user_id"].decode("utf-8"),
        username=raw["username"].decode("utf-8"),
        email=raw["email"].decode("utf-8"),
    )


def delete_registration_challenge(user_id: str):
    REGISTRATION_CHALLENGES.delete(user_id)


## --------------------- Registration Flow --------------------- ##


@dataclass
class VerificationData:
    user_id: str
    credential_id: str
    credential_raw_id: str
    client_data_json: str
    attestation_object: str
    service_id: str
    origin: str


async def register_start(
    username: str, email: str, rp_name: str, service_id: str
) -> dict:
    user_id: str = str(uuid.uuid4())

    options = generate_registration_options(
        rp_id=service_id,
        rp_name=rp_name,
        user_id=bytes(user_id, "utf-8"),
        user_name=username,
        user_display_name=username,
        attestation=AttestationConveyancePreference.DIRECT,
    )

    store_registration_challenge(
        user_id,
        RegistrationChallenge(
            challenge=options.challenge,
            user_id=user_id,
            username=username,
            email=email,
        ),
    )

    return options_to_json_dict(options)


async def register_finish(data: VerificationData) -> dict:
    # Decode base64url fields
    data.user_id = base64url_to_bytes(data.user_id).decode("utf-8")
    data.credential_raw_id = base64url_to_bytes(data.credential_raw_id)

    # Lookup stored registration data
    registration_data: RegistrationChallenge = get_registration_challenge(data.user_id)

    if not registration_data:
        raise UnknownRegistrationFlowError()

    # Verify registration response
    verified_registration = verify_registration_response(
        credential=RegistrationCredential(
            id=data.credential_id,
            raw_id=data.credential_raw_id,
            response=AuthenticatorAttestationResponse(
                client_data_json=base64url_to_bytes(data.client_data_json),
                attestation_object=base64url_to_bytes(data.attestation_object),
            ),
        ),
        expected_challenge=registration_data.challenge,
        expected_rp_id=data.service_id,
        expected_origin=data.origin,
        require_user_verification=True,
    )

    # Passkey name
    passkey_name = "Passkey"
    if b"Yubico" in verified_registration.attestation_object:
        passkey_name = "YubiKey"

    # Clean up stored registration data
    delete_registration_challenge(data.user_id)

    await insert_user(
        UserData(
            _id=registration_data.user_id,
            username=registration_data.username,
            email=registration_data.email,
            passkey_credentials=[
                PasskeyCredential(
                    id=data.credential_id,
                    public_key=verified_registration.credential_public_key,
                    sign_count=verified_registration.sign_count,
                    name=passkey_name,
                )
            ],
            password_credentials=None,
            permissions=DEFAULT_USER_PERMISSIONS,
        )
    )

    return {
        "username": registration_data.username,
        "user_id": registration_data.user_id,
        "email": registration_data.email,
    }


## --------------------- Password Registration --------------------- ##


async def register_with_password(username: str, email: str, password: str) -> dict:
    salt: bytes = bcrypt.gensalt()
    password_hash: bytes = bcrypt.hashpw(password.encode("utf-8"), salt)

    user_id: str = str(uuid.uuid4())
    await insert_user(
        UserData(
            _id=user_id,
            username=username,
            email=email,
            passkey_credentials=[],
            password_credentials=PasswordCredential(
                password_hash=password_hash,
            ),
            permissions=DEFAULT_USER_PERMISSIONS,
        )
    )

    return {
        "username": username,
        "user_id": user_id,
        "email": email,
    }


########################################


# Base passkey registration
async def register_passkey_start(
    user_id: str, username: str, email: str, rp_name: str, service_id: str
) -> dict:
    options = generate_registration_options(
        rp_id=service_id,
        rp_name=rp_name,
        user_id=bytes(user_id, "utf-8"),
        user_name=username,
        user_display_name=username,
        attestation=AttestationConveyancePreference.DIRECT,
    )

    store_passkey_challenge(
        user_id,
        PasskeyChallenge(challenge=options.challenge, user_id=user_id),
    )

    return options_to_json_dict(options)


async def register_passkey_finish(data: VerificationData) -> dict:
    # Decode base64url fields
    data.user_id = base64url_to_bytes(data.user_id).decode("utf-8")
    data.credential_raw_id = base64url_to_bytes(data.credential_raw_id)

    # Lookup stored registration data
    registration_data: PasskeyChallenge = get_passkey_challenge(data.user_id)

    if not registration_data:
        raise UnknownRegistrationFlowError()

    # Verify registration response
    verified_registration = verify_registration_response(
        credential=RegistrationCredential(
            id=data.credential_id,
            raw_id=data.credential_raw_id,
            response=AuthenticatorAttestationResponse(
                client_data_json=base64url_to_bytes(data.client_data_json),
                attestation_object=base64url_to_bytes(data.attestation_object),
            ),
        ),
        expected_challenge=registration_data.challenge,
        expected_rp_id=data.service_id,
        expected_origin=data.origin,
        require_user_verification=True,
    )

    # Passkey name
    passkey_name = "Passkey"
    if b"Yubico" in verified_registration.attestation_object:
        passkey_name = "YubiKey"

    # Clean up stored registration data
    delete_passkey_challenge(data.user_id)

    # Add passkey to user

    pk = PasskeyCredential(
        id=data.credential_id,
        public_key=verified_registration.credential_public_key,
        sign_count=verified_registration.sign_count,
        name=passkey_name,
    )

    await add_passkey(registration_data.user_id, pk)

    return {"status": "ok", "credential_id": data.credential_id}
