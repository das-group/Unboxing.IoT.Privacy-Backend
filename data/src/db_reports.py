import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Literal

from pymongo.errors import DuplicateKeyError
from src.config import (
    MONGO_COLLECTION_REPORTS_FIRMWARE,
    MONGO_COLLECTION_REPORTS_NET,
    MONGO_COLLECTION_REPORTS_POLICY,
)
from src.database import DATA_DB
from src.db_meta import add_report_to_entry, check_metadata_entry_exists
from src.errors import EntryIDNotFoundError, ReportIDNotFoundError


@dataclass
class Report:
    _id: str
    entry_id: str
    created_at: str
    user_id: str
    report_data: dict
    status: str | None = None
    report_type: str | None = None


async def add_report(
    typ: Literal["policy", "net", "firmware"],
    entry_id: str,
    user_id: str,
    report_data: dict,
    report_id: str | None = None,
    status: str | None = "DONE",
    report_type: str | None = None,
) -> str:
    """Add a policy analysis report to the database."""

    if not await check_metadata_entry_exists(entry_id):
        raise EntryIDNotFoundError(entry_id)

    collection = None
    match typ:
        case "policy":
            collection = MONGO_COLLECTION_REPORTS_POLICY
        case "net":
            collection = MONGO_COLLECTION_REPORTS_NET
        case "firmware":
            collection = MONGO_COLLECTION_REPORTS_FIRMWARE

    report_collection = DATA_DB.get_collection(collection)

    while True:
        try:
            if report_id is None:
                report_id = uuid.uuid4().hex
            # created_at = date.now().isoformat()
            created_at = datetime.now(timezone.utc).isoformat()

            _result = await report_collection.insert_one(
                asdict(
                    Report(
                        _id=report_id,
                        entry_id=entry_id,
                        created_at=created_at,
                        user_id=user_id,
                        report_data=report_data,
                        status=status,
                        report_type=report_type,
                    )
                )
            )

            await add_report_to_entry(
                typ, entry_id, report_id, user_id, status, report_type
            )

            return report_id

        except DuplicateKeyError:
            pass


async def get_report(
    typ: Literal["policy", "net", "firmware"], report_id: str
) -> Report:
    """Retrieve a report by its ID."""

    collection = None
    match typ:
        case "policy":
            collection = MONGO_COLLECTION_REPORTS_POLICY
        case "net":
            collection = MONGO_COLLECTION_REPORTS_NET
        case "firmware":
            collection = MONGO_COLLECTION_REPORTS_FIRMWARE

    report_collection = DATA_DB.get_collection(collection)

    document = await report_collection.find_one({"_id": report_id})

    if document:
        return Report(**document)

    raise ReportIDNotFoundError(report_id)
