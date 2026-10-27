from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.processing import submit_analysis_task

router = APIRouter()


class PolicyData(BaseModel):
    entry_id: str
    user_id: str
    type: Literal["url", "html"]
    content: str  # URL or HTML content
    additional: str | None = None  # IF HTML: source url


@router.post("/upload")
def upload(data: PolicyData):
    submit_analysis_task(
        data.entry_id, data.user_id, data.type, data.content, data.additional
    )

    return JSONResponse(
        content={"message": "Data accepted for processing"}, status_code=202
    )
