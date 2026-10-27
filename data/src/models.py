from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from src.generate import generate_enums

# THIS CALL MUST HAPPEN BEFORE IMPORTING THE GENERATED ENUMS
generate_enums()
from src.generated.generated_enums import DeviceCategories


class Report(BaseModel):
    id: str
    added_at: str| None = None
    added_by: str| None = None
    status: str | None = None
    report_type: str | None = None

class Image(BaseModel):
    id: str
    uploaded_at: str
    uploaded_by: str

class CompanionApp(BaseModel):
    id: str | None
    store_link: Optional[str] = None
    name: Optional[str] = None
    developer: Optional[str] = None  
    version: Optional[str] = None
    in_app_purchases: Optional[bool] = None
    free: Optional[bool] = None
    ad_supported: Optional[bool] = None
    contains_ads: Optional[bool] = None
    permissions: Optional[Dict[str, List[str]]] = None
    updated: Optional[int] = None
    last_updated_at: Optional[str] = None

class CompanionApps(BaseModel):
    android: Optional[CompanionApp] = None
    ios: Optional[CompanionApp] = None
    
    
class CompanionAppLinks(BaseModel):
    android: str | None = None
    ios: str | None = None
 
class DeviceEntry(BaseModel):
    id: str = Field(..., alias="_id")
    created_by: str
    created_by_user_id: str
    created_at: str
    last_modified_at: str
    modified_by: str | None = None
    prev_version_id: str | None = None
    manufacturer: str
    model: str
    categories: list[DeviceCategories]
    tags: list[str]
    model_year: int | None
    model_version: str | None
    description: str | None

    title_image: str | None
    images: list[Image]
    policy_reports: List[Report] = Field(default_factory=list)
    net_reports: List[Report] = Field(default_factory=list)
    firmware_reports: List[Report] = Field(default_factory=list)
    
    companion_apps: Optional[CompanionApps] = None

    # JSON dump until structure is finalized
    privacy_properties: dict | None = None
    
    visibility: str | None
    avg_rating: float | None = None
    n_ratings: int | None = None

    class Config:
        validate_by_name = True

class DeviceEntryDiff(BaseModel):
    manufacturer: str | None = None
    model: str | None = None
    categories: list[DeviceCategories] | None = None
    tags: list[str] | None = None
    model_year: int | None = None
    model_version: str | None = None
    description: str | None = None
    companion_app_links: CompanionAppLinks | None = None

class DeviceEntryUpdate(BaseModel):
    id: str = Field(..., alias="_id")
    entry_id: str
    created_at: str
    created_by: str

    diff: DeviceEntryDiff

class EntryReport(BaseModel):
    id: str = Field(..., alias="_id")
    entry_id: str
    created_at: str
    created_by: str
    comment: str
    status: str


class EntryRating(BaseModel):
    entry_id: str
    user_id: str
    rating: int
