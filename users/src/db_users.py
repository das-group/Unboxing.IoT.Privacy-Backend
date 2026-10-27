import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult
from src.config import (
    MONGO_COLLECTION,
    MONGO_DB,
    MONGO_HOST,
    MONGO_PASS,
    MONGO_PORT,
    MONGO_USER,
)
from src.errors import (
    EmailAlreadyExistsError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)

## --------------------- MongoDB Setup --------------------- ##

URI: str = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}"
CLIENT: AsyncMongoClient = AsyncMongoClient(URI)

USERS_DB: AsyncDatabase = CLIENT.get_database(MONGO_DB)


## --------------------- User Data Model and Functions --------------------- ##


@dataclass
class PasskeyCredential:
    id: str
    public_key: bytes
    sign_count: int
    name: str
    creation_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PasswordCredential:
    password_hash: bytes


@dataclass
class UserData:
    _id: str
    username: str
    username_normalized: str = field(init=False)
    email: str
    email_normalized: str = field(init=False)

    passkey_credentials: list[PasskeyCredential]
    password_credentials: PasswordCredential | None

    role_admin: bool = False
    role_contributor: bool = False

    permissions: list[str] = field(default_factory=list)

    settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.username_normalized = self.username.lower()
        self.email_normalized = self.email.lower()


def _user_from_doc(doc: dict) -> UserData:
    return UserData(
        _id=doc["_id"],
        username=doc["username"],
        email=doc["email"],
        passkey_credentials=[
            PasskeyCredential(
                id=cred["id"],
                public_key=cred["public_key"],
                sign_count=cred["sign_count"],
                creation_date=cred["creation_date"],
                name=cred["name"],
            )
            for cred in doc.get("passkey_credentials", [])
        ],
        password_credentials=(
            PasswordCredential(
                password_hash=doc["password_credentials"]["password_hash"],
            )
            if doc.get("password_credentials")
            else None
        ),
        role_admin=doc.get("role_admin", False),
        role_contributor=doc.get("role_contributor", False),
        permissions=doc.get("permissions", []),
        settings=doc.get("settings", {}),
    )


async def initialize_db():
    """Create necessary indexes in the MongoDB collection."""

    users = USERS_DB.get_collection(MONGO_COLLECTION)

    await users.create_index("email_normalized", unique=True, name="email_idx")
    await users.create_index("username_normalized", unique=True, name="username_idx")
    await users.create_index("expires_at", name="expires_at", expireAfterSeconds=0)

async def insert_user(data: UserData):
    """Inserts a new user entry. Returns the user ID."""
    users = USERS_DB.get_collection(MONGO_COLLECTION)

    try:
        res: InsertOneResult = await users.insert_one(
            {
                "_id": data._id,
                "username": data.username,
                "username_normalized": data.username_normalized,
                "email": data.email,
                "email_normalized": data.email_normalized,
                "expires_at": "",
                "passkey_credentials": [cred.__dict__ for cred in data.passkey_credentials],
                "password_credentials": (
                    data.password_credentials.__dict__
                    if data.password_credentials else None
                ),
                "role_admin": data.role_admin,
                "role_contributor": data.role_contributor,
                "permissions": data.permissions,
                "settings": data.settings,
            }
        )

        if not res.acknowledged:
            print("DICT: ", res.__dict__)

    except DuplicateKeyError as e:
        assert e.details is not None
        key = e.details["keyValue"].keys()

        if "username_normalized" in key:
            raise UsernameAlreadyExistsError()
        if "email_normalized" in key:
            raise EmailAlreadyExistsError()

        raise e

    except Exception as e:
        print("Error inserting user: ", e)
        raise e

async def reserve_user(username: str, email: str) -> str:
    """Reserve a user entry with an expiration time. Returns the user ID."""

    users = USERS_DB.get_collection(MONGO_COLLECTION)

    while True:
        user_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(seconds=120)

        try:
            res: InsertOneResult = await users.insert_one(
                {
                    "_id": user_id,
                    "username": username,
                    "username_normalized": username.lower(),
                    "email": email,
                    "email_normalized": email.lower(),
                    "expires_at": expires_at,
                }
            )

            if not res.acknowledged:
                print("DICT:  ", res.__dict__)

            return user_id

        except DuplicateKeyError as e:
            assert e.details is not None
            key = e.details["keyValue"].keys()

            if "username_normalized" in key:
                raise UsernameAlreadyExistsError()
            if "email_normalized" in key:
                raise EmailAlreadyExistsError()

            if "_id" in key:
                print("UUID collision, retrying...")
                continue

            raise e

        except Exception as e:
            print("Error reserving user:", e)
            raise e


async def set_reserved_user(user: UserData) -> bool:
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    res: UpdateResult = await users.update_one(
        filter={
            "_id": user._id,
            "username_normalized": user.username.lower(),
            "email_normalized": user.email.lower(),
        },
        update={
            "$set": {
                "passkey_credentials": [
                    cred.__dict__ for cred in user.passkey_credentials
                ],
                "password_credentials": (
                    user.password_credentials.__dict__
                    if user.password_credentials
                    else None
                ),
                "role_admin": False,
                "role_contributor": False,
                "permissions": user.permissions,
            },
            "$unset": {"expires_at": ""},
        },
    )
    return res.acknowledged


async def _get_user_by_field(field: str, value: str) -> UserData:
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    try:
        user = await users.find_one({field: value})
        if user:
            return _user_from_doc(user)

        raise UserNotFoundError()

    except Exception as e:
        print(f"Error fetching user by {field}:", e)
        raise e


# Todo: maybe limit amount returned
async def get_all_users():
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    try:
        users_cursor = users.find({})

        return [
            {
                "id": user["_id"],
                "username": user["username"],
                "email": user["email"],
                "permissions": user["permissions"],
            }
            async for user in users_cursor
        ]

    except Exception as e:
        print("Error fetching user list:", e)
        raise e


async def get_user_by_id(user_id: str) -> UserData:
    return await _get_user_by_field("_id", user_id)


async def get_user_by_username(username: str) -> UserData:
    return await _get_user_by_field("username_normalized", username.lower())


async def get_user_by_email(email: str) -> UserData:
    return await _get_user_by_field("email_normalized", email.lower())


async def username_update(user_id: str, new_username: str) -> bool:
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    try:
        res: UpdateResult = await users.update_one(
            filter={"_id": user_id},
            update={
                "$set": {
                    "username": new_username,
                    "username_normalized": new_username.lower(),
                }
            },
        )
        if res.matched_count == 0:
            raise UserNotFoundError()

        if res.matched_count > 0 and res.modified_count == 0:
            # No modification made, username might be the same
            return False
        return True

    except DuplicateKeyError:
        raise UsernameAlreadyExistsError()

    except Exception as e:
        print(f"Error updating username for user {user_id}:", e)
        raise e


async def add_passkey(user_id: str, credential: PasskeyCredential):
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    try:
        res: UpdateResult = await users.update_one(
            filter={"_id": user_id},
            update={"$push": {"passkey_credentials": credential.__dict__}},
        )
        if res.matched_count == 0:
            raise UserNotFoundError()

        if res.matched_count > 0 and res.modified_count == 0:
            # No modification made, username might be the same
            return False
        return True

    except Exception as e:
        print(f"Error adding passkey for user {user_id}:", e)
        raise e


async def delete_passkey(user_id: str, passkey_id: str):
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    try:
        res: UpdateResult = await users.update_one(
            filter={"_id": user_id},
            update={"$pull": {"passkey_credentials": {"id": passkey_id}}},
        )
        if res.matched_count == 0:
            raise UserNotFoundError()

        if res.matched_count > 0 and res.modified_count == 0:
            # No modification made, username might be the same
            return False
        return True

    except Exception as e:
        print(f"Error removing passkey for user {user_id}:", e)
        raise e


async def update_user(user_id, username=None, email=None, permissions=None):
    update_dict = {}
    if username is not None:
        update_dict["username"] = username
    if email is not None:
        update_dict["email"] = email
    if permissions is not None:
        update_dict["permissions"] = permissions

    users = USERS_DB.get_collection(MONGO_COLLECTION)
    try:
        res: UpdateResult = await users.update_one(
            filter={"_id": user_id},
            update={"$set": update_dict},
        )
        if res.matched_count == 0:
            raise UserNotFoundError()

        if res.modified_count == 0:
            return False
        return True

    except Exception as e:
        print(f"Error updating user {user_id}:", e)
        raise e


async def delete_user(user_id):
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    try:
        res: DeleteResult = await users.delete_one({"_id": user_id})
        if res.deleted_count != 1:
            raise UserNotFoundError()

        return True

    except Exception as e:
        print(f"Error deleting user {user_id}:", e)
        raise e

async def get_settings_for_user(user_id: str) -> dict[str, Any]:
    user = await get_user_by_id(user_id)
    return user.settings

async def set_settings_for_user(user_id: str, settings: dict[str, Any]) -> bool:
    users = USERS_DB.get_collection(MONGO_COLLECTION)
    res: UpdateResult = await users.update_one(
        filter={"_id": user_id},
        update={"$set": {"settings": settings}},
    )

    return res.matched_count == 1
