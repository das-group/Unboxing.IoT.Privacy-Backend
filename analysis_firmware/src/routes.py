from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.processing import submit_analysis_task



router = APIRouter()

@router.route("/")
def index():
    return "Welcome to Analysis Net!"

@router.post("/upload")
async def file_upload(
    entry_id: str = Form(...),
    file: UploadFile = Form(...),
    model_name: str = Form(...),
    manufacturer_name: str = Form(...),
    user_id: str = Form(...),
):
    file_data = await file.read()
    
    print('Received', len(file_data))
    
    submit_analysis_task(user_id, entry_id, model_name, manufacturer_name, file_data)

    return JSONResponse({"status": "upload_complete"}, status_code=201)
