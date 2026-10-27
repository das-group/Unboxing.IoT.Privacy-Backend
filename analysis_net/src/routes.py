from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.processing import submit_analysis_task
from src.upload import receive_chunk

router = APIRouter()


class UploadComplete(BaseModel):
    upload_id: str
    mac_address: str
    user_id: str
    upload_type: str


@router.post("/upload/complete")
async def upload_complete(data: UploadComplete):
    submit_analysis_task(data.upload_id, data.mac_address, data.user_id, data.upload_type)

    return JSONResponse({"status": "acknowledged"}, status_code=200)


@router.post("/receive-chunk")
async def chunk_upload(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = Form(...),
):
    chunk_bytes = await chunk.read()
    result = await receive_chunk(upload_id, chunk_index, total_chunks, chunk_bytes)

    if result is None:
        return JSONResponse(
            {"status": "chunk_received", "chunk": chunk_index}, status_code=202
        )

    return JSONResponse({"status": "upload_complete"}, status_code=201)
