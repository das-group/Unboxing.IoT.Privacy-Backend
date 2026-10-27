import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Literal
from urllib.parse import parse_qs, urlparse

import pymongo
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from src.config import (
    MONGO_COLLECTION_ENTRY_RATINGS,
    MONGO_COLLECTION_ENTRY_REPORTS,
    MONGO_COLLECTION_ENTRY_UPDATES,
    MONGO_COLLECTION_METADATA,
    MONGO_COLLECTION_REPORTS_FIRMWARE,
    MONGO_COLLECTION_REPORTS_NET,
    MONGO_COLLECTION_REPORTS_POLICY,
)
from src.database import DATA_DB
from src.errors import EntryIDNotFoundError, ImageIDNotAssociatedError
from src.models import (
    CompanionApp,
    CompanionApps,
    DeviceCategories,
    DeviceEntry,
    DeviceEntryDiff,
    DeviceEntryUpdate,
    EntryReport,
    Image,
    Report,
)


@dataclass
class CreateOutput:
    id: str
    created_at: str


async def create_metadata_entry(
    user_id: str,
    user_name: str,
    manufacturer: str,
    model: str,
    categories: list[DeviceCategories],
    tags: list[str],
    model_year: int | None,
    model_version: str | None,
    description: str | None,
    visibility: str | None,
    companion_apps: CompanionApps | None,
    privacy_properties: dict | None,
) -> CreateOutput:
    """Create a new metadata entry in the database and return its ID."""

    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    tags = list(set([tag.lower() for tag in tags]))

    while True:
        try:
            id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()

            _result = await metadata_collection.insert_one(
                DeviceEntry(
                    _id=id,
                    created_by=user_name,
                    created_by_user_id=user_id,
                    created_at=created_at,
                    last_modified_at=created_at,
                    manufacturer=manufacturer,
                    model=model,
                    categories=categories,
                    tags=tags,
                    model_year=model_year,
                    model_version=model_version,
                    description=description,
                    title_image=None,
                    images=[],
                    policy_reports=[],
                    net_reports=[],
                    firmware_reports=[],
                    companion_apps=companion_apps,
                    visibility=visibility,
                    privacy_properties=privacy_properties,
                ).model_dump(by_alias=True)
            )

            return CreateOutput(id=id, created_at=created_at)

        except DuplicateKeyError:
            pass


# Search helper functions
def tokenize(query: str):
    return [t for t in query.strip().split() if t]


def escape_tokens(tokens):
    return [re.escape(t) for t in tokens]


def build_search_query(query: str):
    tokens = tokenize(query)

    if not tokens:
        return {}

    tokens = escape_tokens(tokens)

    return {
        "$and": [
            {
                "$or": [
                    {"manufacturer": {"$regex": token, "$options": "i"}},
                    {"model": {"$regex": token, "$options": "i"}},
                    {"description": {"$regex": token, "$options": "i"}},
                    {"tags": {"$regex": token, "$options": "i"}},
                ]
            }
            for token in tokens
        ]
    }


async def get_metadata_entries(
    count: int, query: str = None, visibility: str = None
) -> list[DeviceEntry]:
    """Retrieve metadata entries from the database."""

    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    if visibility:
        if query:
            # Regex search could be slow with many entries but oh well.
            # TODO when we have more than 10k posts
            cursor = (
                metadata_collection.find(
                    {"visibility": visibility, **build_search_query(query)}
                )
                .sort("created_at", pymongo.DESCENDING)
                .limit(count)
            )
        else:
            cursor = (
                metadata_collection.find({"visibility": visibility})
                .sort("created_at", pymongo.DESCENDING)
                .limit(count)
            )
    else:
        cursor = (
            metadata_collection.find()
            .sort("created_at", pymongo.DESCENDING)
            .limit(count)
        )

    entries = []

    async for document in cursor:
        entries.append(DeviceEntry(**document))

    return entries

async def get_metadata_entries_for_user(
    count: int, user_id: str, query: str = None
) -> list[DeviceEntry]:
    """Retrieve metadata entries from the database."""

    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    if query:
        # Regex search could be slow with many entries but oh well.
        # TODO when we have more than 10k posts
        cursor = (
            metadata_collection.find(
                {"created_by_user_id": user_id, **build_search_query(query)}
            )
            .sort("created_at", pymongo.DESCENDING)
            .limit(count)
        )
    else:
        cursor = (
            metadata_collection.find(
                {
                    "created_by_user_id": user_id,
                }
            )
            .sort("created_at", pymongo.DESCENDING)
            .limit(count)
        )

    entries = []

    async for document in cursor:
        entries.append(DeviceEntry(**document))

    return entries


async def get_metadata_entry_by_id(entry_id: str) -> DeviceEntry | None:
    """Retrieve a metadata entry by its ID."""

    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    document = await metadata_collection.find_one({"_id": entry_id})

    if document:
        return DeviceEntry(**document)

    return None


async def check_metadata_entry_exists(entry_id: str) -> bool:
    """Check if a metadata entry exists in the database."""

    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    document = await metadata_collection.find_one({"_id": entry_id})

    return document is not None


# Used by db_reprots
async def add_report_to_entry(
    typ: Literal["policy", "net", "firmware"],
    entry_id: str,
    report_id: str,
    user_id: str,
    status: str,
    report_type: str,
):
    """Add a policy analysis report to the database."""

    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.find_one_and_update(
        {
            "_id": entry_id,
        },
        {
            "$addToSet": {
                f"{typ}_reports": Report(
                    id=report_id,
                    # added_at=date.now().isoformat(),
                    added_at=datetime.now(timezone.utc).isoformat(),
                    added_by=user_id,
                    status=status,
                    report_type=report_type,
                ).model_dump()
            },
            # "$set": {"last_modified_at": date.now().isoformat()},
            "$set": {"last_modified_at": datetime.now(timezone.utc).isoformat()},
        },
        return_document=True,
    )


async def add_image_to_entry(entry_id: str, image_id: str, user_id: str) -> DeviceEntry:
    """Add an image reference to a metadata entry."""

    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.find_one_and_update(
        {
            "_id": entry_id,
        },
        {
            "$addToSet": {
                "images": Image(
                    id=image_id,
                    # uploaded_at=date.now().isoformat(),
                    uploaded_at=datetime.now(timezone.utc).isoformat(),
                    uploaded_by=user_id,
                ).model_dump()
            },
            # "$set": {"last_modified_at": date.now().isoformat()},
            "$set": {"last_modified_at": datetime.now(timezone.utc).isoformat()},
        },
        return_document=True,
    )

    return DeviceEntry(**res)

async def remove_image_refs(image_id: str):
    """Removes all references to a specified image."""
    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    await collection.update_many(
        {},
        {
            "$pull": { "images": image_id },
        }
    )

    await collection.update_many(
        { "title_image": image_id },
        {
            "$set": { "title_image": None },
        }
    )

async def add_title_image_to_entry(
    entry_id: str,
    image_id: str,
) -> DeviceEntry:
    """Set the title image for a metadata entry."""

    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.find_one_and_update(
        {
            "_id": entry_id,
            "images.id": image_id,
        },
        {
            "$set": {
                "title_image": image_id,
                "last_modified_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    print(res)

    if res is None:
        raise ImageIDNotAssociatedError(image_id)

    return DeviceEntry(**res)


class Visibility(StrEnum):
    Public = "public"
    Review = "review"
    DeleteRequested = "delete_requested"


async def set_visibility(
    entry_id: str,
    visibility: Visibility,
) -> DeviceEntry:
    """Set the visibility for a metadata entry."""

    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.find_one_and_update(
        {
            "_id": entry_id,
        },
        {
            "$set": {
                "visibility": str(visibility),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    return res


async def count_entries_by_visibility(visibility: Visibility) -> int:
    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.count_documents({"visibility": str(visibility)})

    return res


async def create_entry_update(
    entry_id: str, user_id: str, update: DeviceEntryDiff
) -> DeviceEntryUpdate:
    """Create a new update to be accepted by an admin."""
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_UPDATES)

    return await collection.insert_one(
        DeviceEntryUpdate(
            _id=str(uuid.uuid4()),
            entry_id=entry_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=user_id,
            diff=update,
        ).model_dump(by_alias=True)
    )


async def delete_update(update_id: str) -> bool:
    """Removes a update entry from the db"""
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_UPDATES)

    return (await collection.delete_one({"_id": update_id})).deleted_count == 1


async def get_all_updates() -> list[DeviceEntryUpdate]:
    """Get all updates from the update DB."""
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_UPDATES)

    return [DeviceEntryUpdate(**update) async for update in collection.find({})]


async def count_pending_update_requests() -> int:
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_UPDATES)

    return await collection.count_documents({})


async def get_update_by_id(update_id: str) -> DeviceEntryUpdate | None:
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_UPDATES)

    document = await collection.find_one({"_id": update_id})

    return DeviceEntryUpdate(**document) if document else None

async def get_updates_by_entry(entry_id: str) -> list[DeviceEntryUpdate]:
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_UPDATES)

    documents = collection.find({"entry_id": entry_id})

    return [DeviceEntryUpdate(**document) async for document in documents]

async def apply_update(
    user_id: str, entry_id: str, diff: DeviceEntryDiff
) -> str | None:
    """Apply the update diff to change a device entry"""
    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    companion_apps = CompanionApps(android=None, ios=None)
    if diff.companion_app_links and (android_link := diff.companion_app_links.android):
        print("Got app link", flush=True)
        android_app = await fetch_android_app_metadata(android_link)

        print(android_app, flush=True)

        companion_apps = CompanionApps(
            android=android_app if isinstance(android_app, CompanionApp) else None,
            ios=None,
        )

        diff.companion_app_links = None
        print(companion_apps, flush=True)

    dump = diff.model_dump(exclude_none=True, exclude_unset=True)
    new_id = str(uuid.uuid4())

    prev = await collection.find_one_and_update(
        {
            "_id": entry_id,
        },
        {
            "$set": dump
            | {
                "last_modified_at": datetime.now(timezone.utc).isoformat(),
                "modified_by": user_id,
                "prev_version_id": new_id,
                "companion_apps": companion_apps.model_dump(exclude_none=True, exclude_unset=True),
            }
        },
    )

    if prev is None:
        return None

    prev = DeviceEntry(**prev)
    prev.id = new_id
    prev.visibility = "outdated"

    res = await collection.insert_one(prev.model_dump(by_alias=True))

    return res.inserted_id


async def add_entry_report(
    entry_id: str, user_id: str, data: str
) -> EntryReport | None:
    """Insert a new entry report into the DB."""
    user_reports = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_REPORTS)

    if await check_metadata_entry_exists(entry_id):
        try:
            return await user_reports.insert_one(
                EntryReport(
                    _id=str(uuid.uuid4()),
                    entry_id=entry_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    created_by=user_id,
                    comment=data,
                    status="pending",
                ).model_dump(by_alias=True)
            )
        except DuplicateKeyError:
            pass
    return None


async def get_entry_reports(entry_id: str, count: int) -> list[EntryReport]:
    """Return `count` reports from an entry."""
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_REPORTS)

    if not await check_metadata_entry_exists(entry_id):
        return []

    return [
        report
        async for report in (
            collection.find({"entry_id": entry_id})
            .sort("created_at", pymongo.DESCENDING)
            .limit(count)
        )
    ]


async def add_or_update_rating(entry_id: str, user_id: str, rating: int) -> bool:
    """Add or update a rating given by a user to an entry."""
    ratings = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_RATINGS)
    entries = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    if (entry := await get_metadata_entry_by_id(entry_id)) is None:
        return False

    res = await ratings.update_one(
        {
            "entry_id": entry_id,
            "user_id": user_id,
        },
        {"$set": {"rating": max(0, min(rating, 5))}},
        upsert=True,
    )

    if res.modified_count == 0 and not res.did_upsert:
        # Fast path if rating did not change
        return True

    aggregation = await ratings.aggregate(
        [
            {"$match": {"entry_id": entry_id}},
            {
                "$group": {
                    "_id": None,
                    "avg_rating": {"$avg": "$rating"},
                }
            },
        ]
    )

    avg_rating = (await aggregation.next())["avg_rating"]

    if entry.n_ratings is None:
        n_ratings = await ratings.count_documents({"entry_id": entry_id})
        update_count = {"$set": {"n_ratings": n_ratings}}
    else:
        # increase the number of ratings if a new one got inserted
        update_count = { "$inc": { "n_ratings": int(res.did_upsert) }}


    res = await entries.update_one(
        {
            "_id": entry_id
        },
        {
            "$set": { "avg_rating": avg_rating }
        } | update_count,
    )

    if res.matched_count == 0:
        raise ValueError(
            f"Could not find entry: {entry_id}. Database state might be inconsistent."
        )

    return True

async def get_entry_rating_by_user(entry_id: str, user_id: str) -> int:
    rating = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_RATINGS)

    return (await rating.find_one({"entry_id": entry_id, "user_id": user_id}))["rating"]

async def set_report_status(
    report_entry_id: str,
    status: str,
):
    """Set the visibility for a metadata entry."""

    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_REPORTS)

    res = await collection.find_one_and_update(
        {
            "_id": report_entry_id,
        },
        {
            "$set": {
                "status": status,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    return True


async def count_pending_reports() -> int:
    """Count the number of pending entry reports."""
    collection = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_REPORTS)

    res = await collection.count_documents({"status": "pending"})

    return res


def make_deleted_device_entry(entry_id: str) -> DeviceEntry:
    return DeviceEntry(
        id=entry_id,
        _id=entry_id,  # in case alias matters internally
        created_by="",
        created_by_user_id="",
        created_at="",
        last_modified_at="",
        manufacturer="",
        model="Gelöscht",
        categories=[],
        tags=[],
        model_year=None,
        model_version=None,
        description="Dieser Eintrag wurde bereits gelöscht und existiert nicht mehr.",
        title_image=None,
        images=[],
        policy_reports=[],
        net_reports=[],
        firmware_reports=[],
        visibility=None,
    )


async def get_reported_entries() -> list[DeviceEntry]:
    """Return all unique entries which were reported by a user."""
    reports = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_REPORTS)

    entry_ids = await reports.distinct("entry_id")

    entries = []
    for entry_id in entry_ids:
        entry = await get_metadata_entry_by_id(entry_id)
        if entry is None:
            entries.append(make_deleted_device_entry(entry_id))
        else:
            entries.append(entry)

    return entries


async def add_firmware_analysis(
    entry_id: str, firmware_id: str, analysis_id: str, status: str
):

    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.find_one_and_update(
        {
            "_id": entry_id,
        },
        {"$addToSet": {"firmware_reports": {"id": firmware_id, "status": status}}},
        return_document=ReturnDocument.AFTER,
    )

    return True


async def set_firmware_analysis(
    entry_id: str, firmware_id: str, analysis_id: str, status: str
):
    """Retrieve metadata entries from the database."""

    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.find_one_and_update(
        {
            "_id": entry_id,
        },
        {
            "$set": {
                "firmware_reports.$[elem].status": status,
                "firmware_reports.$[elem].analysis_id": analysis_id,
            }
        },
        array_filters=[{"elem.id": firmware_id}],
        return_document=ReturnDocument.AFTER,
    )

    return True


async def remove_firmware_analysis_placeholder(entry_id: str, firmware_id: str):
    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    res = await collection.update_one(
        {"_id": entry_id}, {"$pull": {"firmware_reports": {"id": firmware_id}}}
    )

    return True


async def delete_entry(entry_id: str):
    """Deletes a metadata entry and all its associated data from the database."""
    # import in the function to avoid circular dependancies
    from src.db_images import delete_stored_images, delete_title_image

    entries = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)
    entry_reports = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_REPORTS)
    entry_ratings = DATA_DB.get_collection(MONGO_COLLECTION_ENTRY_RATINGS)
    reports_net = DATA_DB.get_collection(MONGO_COLLECTION_REPORTS_NET)
    reports_firmware = DATA_DB.get_collection(MONGO_COLLECTION_REPORTS_FIRMWARE)
    reports_policy = DATA_DB.get_collection(MONGO_COLLECTION_REPORTS_POLICY)

    entry = await get_metadata_entry_by_id(entry_id)
    if entry is None:
        raise EntryIDNotFoundError(entry_id)

    try:
        # async with await DATA_DB.client.start_session().bind():
        if entry.title_image and await delete_title_image(entry.title_image):
            print("Deleted title image db entry.")

        if entry.images and (res := await delete_stored_images(entry.images)):
            print(f"Deleted {res} images.")

        res = await reports_policy.delete_many(
            {"_id": list(map(lambda x: x.id, entry.policy_reports))}
        )
        print(f"Deleted {res.deleted_count} policy reports.")

        res = await reports_net.delete_many(
            {"_id": list(map(lambda x: x.id, entry.net_reports))}
        )
        print(f"Deleted {res.deleted_count} net reports.")

        res = await reports_firmware.delete_many(
            {"_id": list(map(lambda x: x.id, entry.firmware_reports))}
        )
        print(f"Deleted {res.deleted_count} firmware reports.")

        res = await entry_ratings.delete_many({"entry_id": entry.id})
        print(f"Deleted {res.deleted_count} entry ratings.")

        res = await entry_reports.delete_many({"entry_id": entry.id})
        print(f"Deleted {res.deleted_count} entry reports.")

        res = await entries.delete_one({"_id": entry.id})
        if res.deleted_count == 1:
            print("Deleted metadata entry.")

    except Exception as e:
        print(f"Could not delete entry {entry.id}:", e)
        return False

    return True


async def get_metadata_entries_pending_firmware_analysis() -> list[DeviceEntry]:
    """Retrieve metadata entries from the database."""

    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    cursor = metadata_collection.find(
        {
            "$or": [
                {"firmware_reports.status": "PENDING"},
                {"firmware_reports.status": "WAITING"},
                {"firmware_reports.status": "PROCESSING"},
            ]
        }
    ).sort("created_at", pymongo.DESCENDING)

    entries = []

    async for document in cursor:
        entries.append(DeviceEntry(**document))

    return entries


from google_play_scraper import app as gplay_app
from google_play_scraper import permissions as gplay_permissions


async def fetch_android_app_metadata(url: str) -> CompanionApp | None:
    try:
        # Extract package ID
        parsed = urlparse(url)
        package_id = parse_qs(parsed.query).get("id", [None])[0]
        if not package_id:
            return None

        app_info = gplay_app(package_id, lang="de", country="de")

        perm_raw = gplay_permissions(package_id, lang="de", country="de")

        return CompanionApp(
            id=package_id,
            store_link=url,
            name=app_info.get("title"),
            version=app_info.get("version"),
            developer=app_info.get("developer"),
            updated=app_info.get("updated"),
            in_app_purchases=app_info.get("inAppPurchases", False),
            free=app_info.get("free", True),
            ad_supported=app_info.get("adSupported", False),
            contains_ads=app_info.get("containsAds", False),
            permissions=perm_raw or {},
            last_updated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        print(f"Failed to fetch Android app from {url}: {e}")
        return None


async def fetch_companion_app(entry_id: str):

    from google_play_scraper import app, permissions

    entries = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    entry = await get_metadata_entry_by_id(entry_id)
    if entry is None:
        raise EntryIDNotFoundError(entry_id)

    if (
        entry.companion_apps
        and entry.companion_apps.android
        and entry.companion_apps.android.store_link
    ):
        parsed = urlparse(entry.companion_apps.android.store_link)

        query_params = parse_qs(parsed.query)
        package_name = query_params.get("id", [None])[0]

        if package_name:
            print(f"Extracted package name: {package_name}", flush=True)

            result = app(package_name, lang="de", country="de")
            print(result, flush=True)

            result = permissions(package_name, lang="de", country="de")
            print(result, flush=True)
            return result
        else:
            print("No 'id' parameter found in URL.", flush=True)

    return False
