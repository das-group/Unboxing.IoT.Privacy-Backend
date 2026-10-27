from fastapi import APIRouter, File, Form, Response, UploadFile, Request, Depends
from pydantic import BaseModel
from src.db_images import save_image, delete_stored_images, hide_stored_image, is_image_hidden
from src.db_meta import (
    add_title_image_to_entry,
    add_entry_report,
    get_entry_reports,
    get_reported_entries,
    set_report_status,
    create_metadata_entry,
    get_metadata_entries,
    get_metadata_entries_for_user,
    get_metadata_entry_by_id,
    set_visibility,
    set_firmware_analysis,
    get_metadata_entries_pending_firmware_analysis,
    add_firmware_analysis,
    remove_firmware_analysis_placeholder,
    delete_entry,
    count_pending_reports,
    count_entries_by_visibility,
    Visibility,
    add_or_update_rating,
    create_entry_update,
    get_all_updates,
    apply_update,
    count_pending_update_requests,
    get_update_by_id,
    delete_update,
    fetch_companion_app,
    fetch_android_app_metadata,
    get_entry_rating_by_user,
    remove_image_refs,
    get_updates_by_entry,
)
from src.db_privacylabel import generate_privacy_label
from src.db_reports import add_report, get_report
from src.models import DeviceCategories, DeviceEntry, EntryReport, CompanionAppLinks, CompanionApps, CompanionApp, DeviceEntryDiff, DeviceEntryUpdate
from src.config import (
    ANALYSIS_NET_SERVICE,
    ANALYSIS_POLICY_SERVICE,
    ANALYSIS_FIRMWARE_SERVICE
)
import httpx

router = APIRouter()


## ---------- Metadata Entry Endpoints ---------- ##


class EntryCreateInput(BaseModel):
    user_id: str
    user_name: str
    manufacturer: str
    model: str
    categories: list[DeviceCategories]
    tags: list[str]
    model_year: int | None = None
    model_version: str | None = None
    description: str | None = None
    companion_app_links: CompanionAppLinks | None = None
    privacy_properties: dict | None = None

@router.put(
    "/entry",
    tags=["Metadata"],
    response_model=DeviceEntry,
    response_model_by_alias=False,
)
async def create_entry(data: EntryCreateInput) -> DeviceEntry:
    
    companion_apps = CompanionApps( android=None, ios=None )
    if data.companion_app_links and data.companion_app_links.android:
        print('Got app link', flush=True)
        android_app = await fetch_android_app_metadata(data.companion_app_links.android)
        
        print(android_app, flush=True)
         
        companion_apps = CompanionApps(
                android=android_app if isinstance(android_app, CompanionApp) else None,
                ios=None
            )
            
        print(companion_apps, flush=True)
    
    
    res = await create_metadata_entry(
        user_id=data.user_id,
        user_name=data.user_name,
        manufacturer=data.manufacturer,
        model=data.model,
        categories=data.categories,
        tags=data.tags,
        model_year=data.model_year,
        model_version=data.model_version,
        description=data.description,
        companion_apps=companion_apps,
        visibility="review",
        privacy_properties=data.privacy_properties,
    )
    
    # Fetch google play
    # permissions = await fetch_companion_app(res.id)

    return DeviceEntry(
        id=res.id,
        created_by=data.user_name,
        created_by_user_id=data.user_id,
        created_at=res.created_at,
        last_modified_at=res.created_at,
        manufacturer=data.manufacturer,
        model=data.model,
        categories=data.categories,
        tags=data.tags,
        description=data.description,
        model_year=data.model_year,
        model_version=data.model_version,
        title_image=None,
        images=[],
        policy_reports=[],
        net_reports=[],
        companion_apps=companion_apps, 
        visibility="review",
    )

@router.post(
    "/entry/{entry_id}/update",
    tags=["Metadata"],
)
async def request_entry_update(request: Request, entry_id: str, update: DeviceEntryDiff):
    entry = await get_metadata_entry_by_id(entry_id)
    user_id = request.headers.get("user_id")
    if entry is None or user_id != entry.created_by_user_id:
        return

    await create_entry_update(entry_id, user_id, update)

@router.patch(
    "/entry/{entry_id}/update",
    tags=["Metadata"],
)
async def update_entry(request: Request, entry_id: str, update: DeviceEntryDiff):
    await apply_update(request.headers["user_id"], entry_id, update)

@router.get(
    "/entry/list",
    tags=["Metadata"],
    response_model=list[DeviceEntry],
    response_model_by_alias=False,
)
async def list_entries(count: int | None = 50, query: str | None = None) -> list[DeviceEntry]:
    """List all public metadata entries."""

    entries = await get_metadata_entries(count=count, query=query, visibility="public")

    return entries


@router.get(
    "/entry/submissions",
    tags=["Metadata"],
    response_model=list[DeviceEntry],
    response_model_by_alias=False,
)
async def list_user_entries(request: Request, count: int | None = 500, query: str | None = None) -> list[DeviceEntry]:
    """List all public metadata entries."""

    entries = []
    user_id = request.headers.get("user_id")
    if user_id and len(user_id) > 0:
        entries = await get_metadata_entries_for_user(count=count, user_id=user_id, query=query)

    return entries


@router.get(
    "/entry/{entry_id}",
    tags=["Metadata"],
    response_model=DeviceEntry,
    response_model_by_alias=False,
)
async def get_entry(entry_id: str) -> DeviceEntry | None:
    """Get a metadata entry by its ID."""

    entry = await get_metadata_entry_by_id(entry_id)

    return entry


@router.delete(
    "/entry/{entry_id}/request",
    tags=["Metadata"],
)
async def user_request_deletion(request: Request, entry_id: str) -> dict:
    """Request post deletion by user."""

    user_id = request.headers.get("user_id")
    if user_id and len(user_id) > 0:
        
        # Check entry owner
        entry = await get_metadata_entry_by_id(entry_id)
        
        if entry.created_by_user_id == user_id:
            await set_visibility(entry_id, Visibility.DeleteRequested)
            return {"status": "OK"}
 
    return {"status": "Error"}

class EntryReportRequest(BaseModel):
    comment: str

@router.post(
    "/entry/{entry_id}/report",
    tags=["Metadata"],
)
async def report_entry(request: Request, entry_id: str, entry_report: EntryReportRequest | None) -> dict:
    """Report entry by user."""

    user_id = request.headers.get("user_id")
    if user_id is None or len(user_id) == 0:
        user_id = "Anonymous"

    comment = entry_report.comment if entry_report else ""
    if await add_entry_report(entry_id, user_id, comment):
        # TODO: maybe hide after reported multiple times?
        # await set_visibility(entry_id, 'reported')
        return {"status": "OK"}

    return {"status": "Error"}

class EntryRating(BaseModel):
    rating: int

@router.post(
    "/entry/{entry_id}/rating",
    tags=["Metadata"],
)
async def rate_entry(request: Request, entry_id: str, data: EntryRating) -> dict:
    """Add a rating to an entry."""

    user_id = request.headers.get("user_id")
    if user_id is None or len(user_id) == 0:
        return {"status": "Error"}

    if await add_or_update_rating(entry_id, user_id, data.rating):
        return {"status": "OK"}

    return {"status": "Error"}

class RatingResult(BaseModel):
    avg_rating: float | None
    my_rating: int | None
    n_ratings: int

@router.get(
    "/entry/{entry_id}/rating",
    tags=["Metadata"],
    response_model=RatingResult
)
async def get_entry_rating(request: Request, entry_id: str) -> RatingResult:
    """Get the average rating for an entry."""

    entry = await get_metadata_entry_by_id(entry_id)
    if entry is None or (entry.avg_rating is None or entry.n_ratings is None):
        return RatingResult(avg_rating=None, my_rating=None, n_ratings=0)

    user_id = request.headers.get("user_id")
    user_rating = None if user_id is None else await get_entry_rating_by_user(entry_id, user_id)

    return RatingResult(avg_rating=entry.avg_rating, my_rating=user_rating, n_ratings=entry.n_ratings)

## --------- Report Upload Endpoints ---------- ##


class ReportUploadRequest(BaseModel):
    entry_id: str
    user_id: str
    report: dict
    report_id: str | None = None
    report_type: str | None = None


class ReportRequest(BaseModel):
    entry_id: str
    report_id: str
    created_at: str
    report: dict
    report_type: str| None = None


@router.post("/report/policy", tags=["Policy Analysis"])
async def policy_upload(data: ReportUploadRequest) -> dict:
    """Upload a new policy file."""
    # Placeholder implementation

    res = await add_report("policy", data.entry_id, data.user_id, data.report)

    return {"status": "OK", "report_id": res}


@router.get("/report/policy/{report_id}", tags=["Policy Analysis"])
async def get_policy_report(report_id: str) -> ReportRequest | None:
    report = await get_report("policy", report_id)

    return ReportRequest(
        entry_id=report.entry_id,
        report_id=report._id,
        created_at=report.created_at,
        report=report.report_data,
    )


@router.post("/report/net", tags=["Network Analysis"])
async def network_upload(data: ReportUploadRequest) -> dict:
    """Upload a new policy file."""

    res = await add_report("net", data.entry_id, data.user_id, data.report, report_type=data.report_type)

    return {"status": "OK", "report_id": res}


@router.get("/report/net/{report_id}", tags=["Network Analysis"])
async def get_net_report(report_id: str) -> ReportRequest | None:
    report = await get_report("net", report_id)

    return ReportRequest(
        entry_id=report.entry_id,
        report_id=report._id,
        created_at=report.created_at,
        report=report.report_data,
        report_type=report.report_type
    )

@router.get("/report/firmware/{report_id}", tags=["Firmware Analysis"])
async def get_firmware_report(report_id: str) -> ReportRequest | None:
    report = await get_report("firmware", report_id)

    return ReportRequest(
        entry_id=report.entry_id,
        report_id=report._id,
        created_at=report.created_at,
        report=report.report_data,
    )


## --------- Image Upload Endpoints ---------- ##


class ImageUploadResponse(BaseModel):
    image_id: str
    entry: DeviceEntry


@router.post("/upload/images", tags=["Images"])
async def image_upload(
    entry_id: str = Form(...),
    user_id: str = Form(...),
    file: UploadFile = File(...),
) -> ImageUploadResponse:
    """Upload an image file."""

    image_id, entry = await save_image(file, entry_id, user_id)

    return ImageUploadResponse(image_id=image_id, entry=entry)


class SetTitleImageRequest(BaseModel):
    entry_id: str
    image_id: str


@router.post("/upload/title_image", tags=["Images"])
async def set_title_image(data: SetTitleImageRequest) -> DeviceEntry:
    """Set the title image for a metadata entry."""

    entry = await add_title_image_to_entry(data.entry_id, data.image_id)

    return entry

# Image deletion endpoint
@router.delete(
    "/images/{image_id}",
    tags=["Images"],
)
async def delete_image(image_id: str):
    """Hard delete image from db and image store, as well as all references to it."""
    await remove_image_refs(image_id)
    await delete_stored_images([image_id])

@router.post(
    "/images/{image_id}/hide",
    tags=["Images"]
)
async def hide_image(image_id: str):
    """Hide image without the need for deletion."""
    await hide_stored_image(image_id)

# Image retrieval endpoint
@router.get(
    "/images/{image_id}/is_hidden",
    tags=["Image"]
)
async def is_hidden(image_id: str) -> bool:
    """Check if an image is hidden/soft deleted."""
    return await is_image_hidden(image_id)

# Privacy Badge generation
@router.get("/entry/{entry_id}/privacylabel", tags=["Privacy Label"])
async def get_privacy_label(entry_id: str) -> dict:
    data, media_type = await generate_privacy_label(entry_id)
    if not data:
        return {"status": "ERROR"}

    return Response(content=data, media_type=media_type)


class SetVisibilityRequest(BaseModel):
    public: bool



class AnonymizeRequest(BaseModel):
    user_id: str
@router.post("/anonymize", tags=["Account deletion"])
async def anonymize_entries(
    data: AnonymizeRequest
):
    entries = await add_firmware_analysis(data.user_id)
    return entries

# Modeation
@router.post("/management/submission/{entry_id}/setVisibility", tags=["Moderation"])
async def approve_entry(entry_id: str, data: SetVisibilityRequest) -> dict:
    visibility = Visibility.Review
    if data.public:
        visibility = Visibility.Public
    await set_visibility(entry_id, visibility)

    return {"status": "OK"}


@router.get("/management/submissions")
async def list_entries_moderated(count: int | None = 500) -> list[DeviceEntry]:
    """List moderated metadata entries."""

    entries = await get_metadata_entries(count=count, visibility="delete_requested")
    entries += await get_metadata_entries(count=count, visibility="review")
   

    return entries

@router.delete("/management/submission/{entry_id}", tags=["Metadata"])
async def delete_entry_handler(entry_id: str) -> dict:
    """Delete metadata entry by its ID."""

    result = await delete_entry(entry_id)

    if result:
        return {"status": "OK"}

    raise NotImplementedError

@router.get(
    "/management/submission/{entry_id}/reports",
    tags=["Metadata"],
    response_model=list[EntryReport],
    response_model_by_alias=False,
)
async def entry_reports(entry_id: str, count: int) -> list[EntryReport]:
    """Get `count` reports for an entry."""
    return await get_entry_reports(entry_id, count)

@router.get(
    "/management/submissions/reported",
    tags=["Metadata"],
)
async def reported_entries(count: int = 500) -> list[DeviceEntry]:
    """Return `count` reported entries."""
    return (await get_reported_entries())[:count]



class UpdateReportStatus(BaseModel):
    status: str
@router.post(
    "/management/report/{report_id}",
    tags=["Moderation"]
)
async def set_report_status_handler(report_id: str, data: UpdateReportStatus) -> dict:
    if not await set_report_status(report_id, data.status):
        return {"status": "Error"}
    return {"status": "OK"}

class Counters(BaseModel):
    delete_req: int
    pending_rep: int
    hidden_entr: int
    update_req: int

@router.get("/management/counters", tags=["Moderation"], response_model=Counters)
async def get_counters() -> Counters:
    return Counters(
        delete_req=await count_entries_by_visibility(Visibility.DeleteRequested),
        pending_rep=await count_pending_reports(),
        hidden_entr=await count_entries_by_visibility(Visibility.Review),
        update_req=await count_pending_update_requests(),
    )

@router.get("/management/updates", tags=["Moderation"])
async def get_updates() -> list[tuple[DeviceEntryUpdate, DeviceEntry]]:
    updates: list[DeviceEntryUpdate] = await get_all_updates()
    return [
        (update, entry) for update in updates if (entry := await get_metadata_entry_by_id(update.entry_id))
    ]

@router.get("/management/updates/{entry_id}", tags=["Moderation"])
async def get_updates_for_entry(entry_id: str) -> list[tuple[DeviceEntryUpdate, DeviceEntry]]:
    updates: list[DeviceEntryUpdate] = await get_updates_by_entry(entry_id)
    return [
        (update, entry) for update in updates if (entry := await get_metadata_entry_by_id(update.entry_id))
    ]

@router.get("/management/update/{update_id}", tags=["Moderation"])
async def get_update(update_id: str) -> tuple[DeviceEntryUpdate, DeviceEntry] | None:
    update = await get_update_by_id(update_id)
    if update is not None and (entry := await get_metadata_entry_by_id(update.entry_id)):
        return (update, entry)

    return None

@router.patch("/management/apply_update", tags=["Moderation"])
async def apply_update_request(update_id: str):
    update = await get_update_by_id(update_id)
    if update is None:
        return

    if await apply_update(update.created_by, update.entry_id, update.diff):
        await delete_update(update_id)

class FirmwareReportCreate(BaseModel):
    entry_id: str
    firmware_id: str
    analysis_id: str | None
    status: str
    data: dict | None

@router.post("/report/firmware/add", tags=["Firmware Analysis"])
async def add_firmware(
    data: FirmwareReportCreate
):

    entries = await add_firmware_analysis(data.entry_id, data.firmware_id, data.analysis_id, data.status)

    return entries
 
@router.post("/report/firmware/set", tags=["Firmware Analysis"])
async def set_firmware_state(
    data: FirmwareReportCreate
):
    entries = await set_firmware_analysis(data.entry_id, data.firmware_id, data.analysis_id, data.status)

    return entries 
    
@router.post("/report/firmware", tags=["Firmware Analysis"])
async def firmware_upload(data: ReportUploadRequest) -> dict:
    
    await remove_firmware_analysis_placeholder(data.entry_id, data.report_id)

    res = await add_report("firmware", data.entry_id, data.user_id, data.report, data.report_id)

    return {"status": "OK", "report_id": res}

@router.get("/report/pending_firmware", tags=["Firmware Analysis"])
async def fetch_pending() -> list[DeviceEntry]:
  
    entries = await get_metadata_entries_pending_firmware_analysis()

    return entries
