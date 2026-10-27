import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, Query
from typing import Optional, Any
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel
from src.auth import (
    SessionInfo,
    get_user_by_token,
    get_user_by_token_optional,
    require_permission,
)
from src.config import (
    ANALYSIS_NET_SERVICE,
    ANALYSIS_POLICY_SERVICE,
    ANALYSIS_FIRMWARE_SERVICE,
    DATA_SERVICE,
    USER_SERVICE
)
from src.errors import InvalidInputError

router = APIRouter()

## ----------------------- Rate Limiting ---------------------- ##

limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=True,
    default_limits=["15 per 10 seconds"],
)

## ----------------------- Entry Endpoint ---------------------- ##


@router.put("/entry", tags=["Entry"])
async def create_data_entry(
    data: dict, 
    user_data: dict = Depends(require_permission("create_post"))
) -> JSONResponse:
    
    data["user_id"] = user_data.user_id
    data["user_name"] = user_data.username

    async with httpx.AsyncClient() as client:
        resp = await client.put(f"http://{DATA_SERVICE}/entry", json=data)

    return process_proxy_response(resp)


"""
@router.get("/entry/list", tags=["Entry"])
async def list_data_entries(count: int = 10) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/entry/list?count={count}")

    return process_proxy_response(resp)


@router.get("/entry/{entry_id}", tags=["Entry"])
async def get_data_entry(entry_id: str) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/entry/{entry_id}")

    return process_proxy_response(resp)
"""

# Priacy Label

# Handler for all /entry requests
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


# Remove some headers for reasons
def filter_headers(headers):
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}


@router.get("/entry/list", tags=["Data Retrieval"])
async def get_entry_list(
    request: Request,
    query: Optional[str] = Query(None),
    user_data: SessionInfo | None = Depends(get_user_by_token_optional),
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{DATA_SERVICE}/entry/list",
            params={"query": query},
        )
        return process_proxy_response(resp)
 
@router.get("/entry/submissions", tags=["Data Retrieval"])
async def get_my_submissions(request: Request, user_data: SessionInfo | None = Depends(get_user_by_token_optional)) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        headers = filter_headers(dict(request.headers))
         
        if user_data:
            headers["user_id"] = str(user_data.user_id)
        else:
            headers.pop("user_id", None) 
        
        resp = await client.get(f"http://{DATA_SERVICE}/entry/submissions",  headers=headers)
       
        return process_proxy_response(resp)
       

# Get handler for entry
@router.get("/entry/{entry_id}", tags=["Data Retrieval"])
async def get_entry_data(entry_id: str, request: Request, user_data: SessionInfo | None = Depends(get_user_by_token_optional)) -> JSONResponse:
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/entry/{entry_id}")
        
        # Resolve username for created_by_user_id field
        data = await resolve_username_extend(resp.json(), 'created_by_user_id', 'created_by_username')
        if 'modified_by' in data and data['modified_by'] is not None:
            data = await resolve_username_extend(data, 'modified_by', 'modified_by_username')

        return process_proxy_response_content(resp, data)

# Update handler for entry
@router.patch("/entry/{entry_id}/update")
async def update_entry_data(entry_id: str, request: Request, user_data: SessionInfo = Depends(get_user_by_token)) -> JSONResponse:
    headers = filter_headers(dict(request.headers))
    headers["user_id"] = str(user_data.user_id)
    body = await request.body()

    async with httpx.AsyncClient() as client:
        if user_data.admin or any(perm in user_data.permissions for perm in ["manage_posts", "*"]):
            resp = await client.patch(
                f"http://{DATA_SERVICE}/entry/{entry_id}/update",
                content=body,
                headers=headers,
            )
        else:
            resp = await client.post(
                f"http://{DATA_SERVICE}/entry/{entry_id}/update",
                content=body,
                headers=headers,
            )

        return process_proxy_response(resp)

# Handler
@router.api_route(
    "/entry/{entry_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    tags=["Entry"],
)
async def proxy_all_entry_handler(entry_path: str, request: Request, user_data: SessionInfo | None = Depends(get_user_by_token_optional)):
    # Build upstream URL
    qs = request.url.query
    upstream_url = f"http://{DATA_SERVICE}/entry/{entry_path}"
    if qs:
        upstream_url += f"?{qs}"

    # Read body
    body = await request.body()

    # Forward headers
    headers = filter_headers(dict(request.headers))
    
    if user_data:
        headers["user_id"] = str(user_data.user_id)
    else:
        headers.pop("user_id", None) 
        
    async with httpx.AsyncClient(follow_redirects=True) as client:
        upstream_response = await client.request(
            request.method,
            upstream_url,
            content=body,
            headers=headers,
        )

    # Error handling
    if upstream_response.status_code >= 400:
        return process_proxy_response(upstream_response)

    # Return response from upstream
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=filter_headers(upstream_response.headers),
        media_type=upstream_response.headers.get("content-type"),
    )

"""
@router.api_route("/user/{user_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"], tags=["User"])
async def proxy_all_user_handler(user_path: str, request: Request, token: str | None = Depends(get_auth_token)):

    print('proxy_all_user_handler')
    # Build upstream URL
    qs = request.url.query
    upstream_url = f"http://{USER_SERVICE}/user22/{user_path}"
    if qs:
        upstream_url += f"?{qs}"

    # Read body
    body = await request.body()

    # Forward headers
    headers = filter_headers(dict(request.headers))
    headers['token'] = token

    print('Filtered Headers:')
    print(headers)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        upstream_response = await client.request(
            request.method,
            upstream_url,
            content=body,
            headers=headers,
        )

    # Error handling
    if upstream_response.status_code >= 400:
        return process_proxy_response(upstream_response)

    # Return response from upstream
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=filter_headers(upstream_response.headers),
        media_type=upstream_response.headers.get("content-type")
    )
"""

## ----------------------- Data Retrieval Endpoints ---------------------- ##


@router.get("/data/policy/{data_id}", tags=["Data Retrieval"])
async def get_policy_data(data_id: str) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/report/policy/{data_id}")

    return process_proxy_response(resp)


@router.get("/data/net/{data_id}", tags=["Data Retrieval"])
async def get_net_data(data_id: str) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{DATA_SERVICE}/report/net/{data_id}")

    return process_proxy_response(response)

@router.get("/data/firmware/{data_id}", tags=["Data Retrieval"])
async def get_firmware_data(data_id: str) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{DATA_SERVICE}/report/firmware/{data_id}")

    return process_proxy_response(response)
    
    
@router.post("/upload/policy/direct", tags=["Data Upload"])
async def data_upload_policy_direct(
    data: dict,
    user_data: SessionInfo = Depends(require_permission("create_post")),
):
    data["user_id"] = user_data.user_id

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"http://{ANALYSIS_POLICY_SERVICE}/upload", json=data)

    return process_proxy_response(resp)



@router.post("/data/policy/{data_id}/refresh", tags=["Data Refresh"])
@limiter.limit("1 per 30 seconds") 
async def refresh_policy_data(request: Request, data_id: str, user_data: SessionInfo = Depends(require_permission("create_post"))) -> JSONResponse:
    
    # Fetch policy info
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/report/policy/{data_id}")
    
    report_info = resp.json()

    data = {}
    data["user_id"] = user_data.user_id
    data['entry_id'] =  report_info['entry_id']
    data['type'] = 'url'
    data['content'] = report_info['report']['source']
    data['additional'] = report_info['report']['source']

    # Submit new policy analysis request
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"http://{ANALYSIS_POLICY_SERVICE}/upload", json=data)

    return process_proxy_response(resp)


## ----------------------- Stream Upload Endpoint ---------------------- ##


class UploadIDOutput(BaseModel):
    upload_id: str


@router.get("/upload-id/{entry_id}", tags=["Data Upload"])
async def get_upload_id(
    entry_id: str,
    user_data: SessionInfo = Depends(require_permission("create_post")),
) -> UploadIDOutput:
    # TODO: Authentication check
    # info = await verify_authentication(token, "contributor")

    id = uuid.uuid4()
    return UploadIDOutput(upload_id=f"{entry_id}_{id.hex}")


@router.post("/upload/net/chunk", tags=["Data Upload"])
async def data_upload_net(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    file_type: str = Form(...),
    chunk: UploadFile = Form(...),
    user_data: SessionInfo = Depends(require_permission("create_post")),
):
    if file_type not in ["pcapng", "pcap"]:
        raise InvalidInputError(
            "Invalid file type for net upload. Only ['pcapng', 'pcap'] are allowed."
        )

    # TODO: verify upload id
    # info = await verify_authentication(token, "contributor")

    dest = f"http://{ANALYSIS_NET_SERVICE}/receive-chunk"
    # print("Proxying to", dest)
    return await proxy_chunk(dest, upload_id, chunk_index, total_chunks, chunk)


@router.post("/upload/policy/chunk", tags=["Data Upload"])
async def data_upload_policy(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    file_type: str = Form(...),
    chunk: UploadFile = Form(...),
    user_data: SessionInfo = Depends(require_permission("create_post")),
):
    # TODO: verify upload id
    # info = await verify_authentication(token, "user")

    dest = f"http://{ANALYSIS_POLICY_SERVICE}/receive-chunk"

    return await proxy_chunk(dest, upload_id, chunk_index, total_chunks, chunk)


async def proxy_chunk(
    destination_url: str,
    upload_id: str,
    chunk_index: int,
    total_chunks: int,
    chunk: UploadFile,
):
    # Read chunk bytes (small, safe)
    data = await chunk.read()

    # Forward chunk to destination
    async with httpx.AsyncClient() as client:
        try:
            result = await client.post(
                destination_url,
                data={
                    "upload_id": upload_id,
                    "chunk_index": str(chunk_index),
                    "total_chunks": str(total_chunks),
                },
                files={"chunk": (chunk.filename, data, chunk.content_type)},
            )
        except httpx.ConnectError as e:
            return JSONResponse(
                content={
                    "error": "Failed to connect to analysis service",
                    "code": "ANALYSIS_SERVICE_UNAVAILABLE",
                    "msg": str(e),
                },
                status_code=502,
            )
        except httpx.ReadTimeout as e:
            return JSONResponse(
                content={
                    "error": "Read timeout from analysis service",
                    "code": "ANALYSIS_SERVICE_TIMEOUT",
                    "msg": str(e),
                },
                status_code=504,
            )

    if result.status_code != 201 and result.status_code != 202:
        return JSONResponse(
            content={
                "error": "Failed to upload chunk",
                "code": result.status_code,
                "msg": result.text,
            },
            status_code=502,
        )

    return JSONResponse(content=result.json(), status_code=result.status_code)


class UploadCompleteNet(BaseModel):
    upload_id: str
    mac_address: str
    upload_type: str

@router.post("/upload/net/complete", tags=["Data Upload"])
async def data_upload_net_complete(
    data: UploadCompleteNet,
    user_data: SessionInfo = Depends(require_permission("create_post")),
):
    # TODO: verify upload id
    # info = await verify_authentication(token, "contributor")

    # TODO: remove timeout
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(
                f"http://{ANALYSIS_NET_SERVICE}/upload/complete",
                json={
                    "upload_id": data.upload_id,
                    "mac_address": data.mac_address,
                    "user_id": user_data.user_id,
                    "upload_type": data.upload_type
                },
            )
        except httpx.ReadTimeout as e:
            print("[ERROR] Read timeout:", str(e))
            return JSONResponse(
                content={
                    "error": "Read timeout from analysis net service",
                    "code": "ANALYSIS_NET_SERVICE_TIMEOUT",
                    "msg": str(e),
                },
                status_code=504,
            )
        except httpx.ConnectError as e:
            print("[ERROR] Connection error:", str(e))
            return JSONResponse(
                content={
                    "error": "Failed to connect to analysis net service",
                    "code": "ANALYSIS_NET_SERVICE_UNAVAILABLE",
                    "msg": str(e),
                },
                status_code=502,
            )

    return process_proxy_response(resp)


class UploadCompletePolicy(BaseModel):
    upload_id: str


@router.post("/upload/policy/complete", tags=["Data Upload"])
async def data_upload_policy_complete(
    data: UploadCompletePolicy,
    user_data: SessionInfo = Depends(require_permission("create_post")),
):
    # TODO: verify upload id
    # info = await verify_authentication(token, "contributor")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"http://{ANALYSIS_POLICY_SERVICE}/upload/complete",
                json={"upload_id": data.upload_id, "user_id": user_data.user_id},
            )
        except httpx.ReadTimeout as e:
            print("[ERROR] Read timeout:", str(e))
            return JSONResponse(
                content={
                    "error": "Read timeout from analysis policy service",
                    "code": "ANALYSIS_POLICY_SERVICE_TIMEOUT",
                    "msg": str(e),
                },
                status_code=504,
            )
        except httpx.ConnectError as e:
            print("[ERROR] Connection error:", str(e))
            return JSONResponse(
                content={
                    "error": "Failed to connect to analysis policy service",
                    "code": "ANALYSIS_POLICY_SERVICE_UNAVAILABLE",
                    "msg": str(e),
                },
                status_code=502,
            )

    return process_proxy_response(resp)


##


@router.post("/upload/policy/direct", tags=["Data Upload"])
async def data_upload_policy_direct(
    data: dict,
    user_data: SessionInfo = Depends(require_permission("create_post")),
):
    data["user_id"] = user_data.user_id

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"http://{ANALYSIS_POLICY_SERVICE}/upload", json=data)

    return process_proxy_response(resp)


## --------- Image Upload Endpoints ---------- ##


@router.post("/upload/image/{entry_id}", tags=["Images"])
async def image_upload(
    entry_id: str,
    file_upload: UploadFile = File(...),
    user_data: SessionInfo = Depends(require_permission("create_post")),
) -> JSONResponse:
    """Upload an image file."""

    assert file_upload is not None and file_upload.filename is not None

    suffix = file_upload.filename.split(".")[-1].lower()
    if suffix not in ["jpeg", "jpg", "png"]:
        raise InvalidInputError(
            "Uploaded image format is not supported. Only '.png', '.jpg', and '.jpeg' are allowed."
        )

    # Send the file using httpx (async HTTP client)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"http://{DATA_SERVICE}/upload/images",
                data={
                    "user_id": user_data.user_id,
                    "entry_id": entry_id,
                },
                files={
                    "file": (
                        file_upload.filename,
                        file_upload.file,
                        file_upload.content_type,
                    )
                },
            )
        except httpx.ReadTimeout as e:
            print("[ERROR] Read timeout:", str(e))
            return JSONResponse(
                content={
                    "error": "Read timeout from data service",
                    "code": "DATA_SERVICE_TIMEOUT",
                    "msg": str(e),
                },
                status_code=504,
            )
        except httpx.ConnectError as e:
            print("[ERROR] Connection error:", str(e))
            return JSONResponse(
                content={
                    "error": "Failed to connect to data service",
                    "code": "DATA_SERVICE_UNAVAILABLE",
                    "msg": str(e),
                },
                status_code=502,
            )

    return process_proxy_response(resp)


@router.get("/uploads/images/{image_id}", tags=["Images"])
async def image_retrieve(image_id: str):
    """Retrieve an image file."""

    if not image_id.endswith(".png"):
        raise InvalidInputError("Image ID must end with .png")

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/images/{image_id}/is_hidden")

    if resp.status_code >= 400:
        return process_proxy_response(resp)

    # print(resp.json(), flush=True)
    if resp.json():
        print("Hiding image", flush=True)
        return Response(
            content="Image could not be found",
            status_code=404
        )

    # Send the file using httpx (async HTTP client)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/uploads/images/{image_id}")

    if resp.status_code >= 400:
        return process_proxy_response(resp)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )


class TitleImageRequest(BaseModel):
    entry_id: str
    image_id: str


@router.post("/upload/title_image", tags=["Images"])
async def set_title_image(
    data: TitleImageRequest,
    user_data: SessionInfo = Depends(require_permission("create_post")),
) -> JSONResponse:
    """Set the title image for a metadata entry."""

    # check entry id author?
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{DATA_SERVICE}/upload/title_image",
            json=data.model_dump(),
        )

    return process_proxy_response(resp)

## ------------------- Image Deletion Endpoints ------------------- ##

@router.delete("/images/{image_id}", tags=["Images"])
async def delete_image(image_id: str, user_data: SessionInfo | None = Depends(get_user_by_token_optional)) -> JSONResponse:
    """Delete or hide image."""

    async with httpx.AsyncClient() as client:
        if user_data and user_data.admin:
            res = await client.delete(f"http://{DATA_SERVICE}/images/{image_id}")
        else:
            res = await client.post(f"http://{DATA_SERVICE}/images/{image_id}/hide")

    return process_proxy_response(res)

## ----------------------- Profile Endpoints ---------------------- ##


class UsernameUpdateRequest(BaseModel):
    new_username: str


@router.post("/user/update/username", tags=["Profile"])
async def update_username(
    data: UsernameUpdateRequest,
    user_data: SessionInfo = Depends(get_user_by_token),
):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{USER_SERVICE}/user/update/username",
            json={
                "new_username": data.new_username,
                "user_id": user_data.user_id,
            },
        )

        return process_proxy_response(resp)

@router.get("/user/settings", tags=["Profile"])
async def dump_settings(data: SessionInfo = Depends(get_user_by_token)):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{USER_SERVICE}/user/{data.user_id}/settings",
        )

        return process_proxy_response(resp)

@router.post("/user/settings", tags=["Profile"])
async def load_settings(settings_dump: dict[str, Any], data: SessionInfo = Depends(get_user_by_token)):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{USER_SERVICE}/user/{data.user_id}/settings",
            json=settings_dump,
        )

        return process_proxy_response(resp)

## ----------------------- Helper Functions ---------------------- ##

# Functions to resolve userid to username, so the client doesn't have to do this manually
async def resolve_userid_to_name(user_id: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{USER_SERVICE}/user/{user_id}")

    if resp.status_code >= 400:
        return None
            
    data = resp.json()
    return data['username']

async def resolve_username_extend(element: Dict[str, Any], userid_field: str, username_field: str) -> Dict[str, Any]:
    if element is None:
        return element
    if isinstance(element, list):
        return element
        
    element[username_field] = await resolve_userid_to_name(element[userid_field])
    return element


def process_proxy_response(resp: httpx.Response) -> JSONResponse:
    if resp.status_code >= 500:
        return JSONResponse(
            content={"code": "INTERNAL_SERVICE_ERROR"},
            status_code=502,
        )

    headers = resp.headers.copy()
    headers["X-Source"] = "Proxied"
    return JSONResponse(
        content=resp.json(), status_code=resp.status_code, headers=headers
    )

def process_proxy_response_content(resp: httpx.Response, data) -> JSONResponse:
    if resp.status_code >= 500:
        return JSONResponse(
            content={"code": "INTERNAL_SERVICE_ERROR"},
            status_code=502,
        )

    headers = resp.headers.copy()
    headers["X-Source"] = "Proxied"
    return JSONResponse(
        content=data, status_code=resp.status_code
    )

# Management


@router.get("/management/submissions", tags=["Moderation"])
@limiter.exempt
async def fetch_submissions(
    user_data: SessionInfo = Depends(require_permission("manage_posts")),
):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{DATA_SERVICE}/management/submissions")

        return process_proxy_response(resp)


@router.post("/management/submission/{entry_id}/setVisibility", tags=["Moderation"])
@limiter.exempt
async def set_post_visibility(
    entry_id: str,
    req_data: dict,
    user_data: SessionInfo = Depends(require_permission("manage_posts")),
):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{DATA_SERVICE}/management/submission/{entry_id}/setVisibility",
            json=req_data,
        )

        return process_proxy_response(resp)

@router.delete("/management/submission/{entry_id}", tags=["Moderation"])
@limiter.exempt
async def delete_submission(
    entry_id: str,
    user_data: dict = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"http://{DATA_SERVICE}/management/submission/{entry_id}"
        )

        return process_proxy_response(resp)


@router.get("/management/submission/{entry_id}/reports", tags=["Moderation"])
@limiter.exempt
async def entry_reports(
    entry_id: str, count: int = 10,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{DATA_SERVICE}/management/submission/{entry_id}/reports",
            params={"count": count}
        )
        
        data = resp.json()

        # Resolve username for user_id fields
        resolved_data = [await resolve_username_extend(d, 'created_by', 'created_by_username') for d in data]

        return process_proxy_response_content(resp, resolved_data)

@router.get("/management/submissions/reported", tags=["Moderation"])
@limiter.exempt
async def reported_entries(
    count: int = 500,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{DATA_SERVICE}/management/submissions/reported",
            params={"count": count}
        )
        
        data = resp.json()

        # Resolve username for user_id fields
        resolved_data = [await resolve_username_extend(d, 'created_by_user_id', 'created_by_username') for d in data]

        return process_proxy_response_content(resp, resolved_data)
        

class UpdateReportStatus(BaseModel):
    status: str
    
@router.post("/management/report/{report_id}", tags=["Moderation"])
@limiter.exempt
async def set_report_status(
    report_id: str,
    data: UpdateReportStatus,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{DATA_SERVICE}/management/report/{report_id}",
            json={"status": data.status}
        )

        return process_proxy_response(resp)        

@router.get("/management/counters", tags=["Moderation"])
@limiter.exempt
async def get_counters(
    _request: Request,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{DATA_SERVICE}/management/counters"
        )

        return process_proxy_response(resp)

async def add_username_to_update(data: tuple[dict[str, Any], dict[str, Any]]):
    update = data[0]
    update = await resolve_username_extend(update, 'created_by', 'created_by_username')
    return (update, data[1])

@router.get("/management/updates", tags=["Moderation"])
@limiter.exempt
async def get_updates(
    _request: Request,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{DATA_SERVICE}/management/updates"
        )

        updates = resp.json()
        data = [await add_username_to_update(x) for x in updates]
        return process_proxy_response_content(resp, data)

@router.get("/management/updates/{entry_id}", tags=["Moderation"])
@limiter.exempt
async def get_update_for_entry(
    entry_id: str,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{DATA_SERVICE}/management/updates/{entry_id}"
        )

        updates = resp.json()
        data = [await add_username_to_update(update) for update in updates]
        return process_proxy_response_content(resp, data)

@router.get("/management/update/{update_id}", tags=["Moderation"])
@limiter.exempt
async def get_update(
    update_id: str,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{DATA_SERVICE}/management/update/{update_id}"
        )

        update = resp.json()
        data = await add_username_to_update(update)

        return process_proxy_response_content(resp, data)

@router.patch("/management/apply_update", tags=["Moderation"])
@limiter.exempt
async def apply_update(
    update_id: str,
    user_data: SessionInfo = Depends(require_permission("manage_posts"))
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"http://{DATA_SERVICE}/management/apply_update",
            params={"update_id": update_id}
        )

        return process_proxy_response(resp)
# Firmware

@router.post("/upload/firmware", tags=["Data Upload"])
async def data_upload_firmware(
    entry_id: str = Form(...),
    file: UploadFile = Form(...),
    model_name: str = Form(...),
    manufacturer_name: str = Form(...),
    user_data: SessionInfo = Depends(require_permission("create_post")),
):
    # TODO: Check if user owns post id

    destination_url = f"http://{ANALYSIS_FIRMWARE_SERVICE}/upload"
    
    file_data = await file.read()
    
    # Forward 
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            result = await client.post(
                destination_url,
                data={
                    "entry_id": entry_id,
                    "model_name": model_name,
                    "manufacturer_name": manufacturer_name,
                    "user_id": user_data.user_id
                },
                files={"file": (file.filename, file_data, file.content_type)},
            )
        except httpx.ConnectError as e:
            return JSONResponse(
                content={
                    "error": "Failed to connect to analysis service",
                    "code": "ANALYSIS_SERVICE_UNAVAILABLE",
                    "msg": str(e),
                },
                status_code=502,
            )
        except httpx.ReadTimeout as e:
            return JSONResponse(
                content={
                    "error": "Read timeout from analysis service",
                    "code": "ANALYSIS_SERVICE_TIMEOUT",
                    "msg": str(e),
                },
                status_code=504,
            )

    if result.status_code != 201 and result.status_code != 202:
        return JSONResponse(
            content={
                "error": "Failed to upload chunk",
                "code": result.status_code,
                "msg": result.text,
            },
            status_code=502,
        )

    return JSONResponse(content=result.json(), status_code=result.status_code)
    




@router.get("/user/{user_id}", tags=["User"])
async def fetch_user_info(user_id: str, request: Request, user_data: SessionInfo | None = Depends(get_user_by_token_optional)):
    """Retrieve an image file."""

    # Forward headers
    headers = filter_headers(dict(request.headers))
    
    # If we have a session, pass the session user id
    if user_data:
        headers["user_id"] = str(user_data.user_id)
    else:
        headers.pop("user_id", None) 

    # Send the file using httpx (async HTTP client)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{USER_SERVICE}/user/{user_id}", headers=headers)

    if resp.status_code >= 400:
        return process_proxy_response(resp)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers,
    )
