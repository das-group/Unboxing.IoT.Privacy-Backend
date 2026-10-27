import asyncio
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from src.config import (
    IMAGE_UPLOAD_DIR,
    MONGO_COLLECTION_IMAGES,
    MONGO_COLLECTION_METADATA,
    MONGO_COLLECTION_ENTRY_REPORTS,
    MONGO_COLLECTION_ENTRY_RATINGS,
    MONGO_COLLECTION_ENTRY_UPDATES,
    MONGO_COLLECTION_REPORTS_NET,
    MONGO_COLLECTION_REPORTS_POLICY,
    MONGO_COLLECTION_REPORTS_FIRMWARE
)
from src.database import DATA_DB
from src.errors import PublicError
from src.routes import router
from starlette.types import Scope

## --------------------- FastAPI Application Lifespan --------------------- ##


@asynccontextmanager
async def lifetime(_app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    try:
        await asyncio.gather(
            *[
                DATA_DB.create_collection(MONGO_COLLECTION_METADATA),
                DATA_DB.create_collection(MONGO_COLLECTION_ENTRY_REPORTS),
                DATA_DB.create_collection(MONGO_COLLECTION_ENTRY_RATINGS),
                DATA_DB.create_collection(MONGO_COLLECTION_ENTRY_UPDATES),
                DATA_DB.create_collection(MONGO_COLLECTION_REPORTS_POLICY),
                DATA_DB.create_collection(MONGO_COLLECTION_REPORTS_NET),
                DATA_DB.create_collection(MONGO_COLLECTION_REPORTS_FIRMWARE),
                DATA_DB.create_collection(MONGO_COLLECTION_IMAGES),
            ]
        )

    except Exception:
        pass

    yield

    # shutdown
    await DATA_DB.client.close()


app = FastAPI(lifespan=lifetime)

##--------------------- Global Exception Handlers --------------------- ##


@app.exception_handler(PublicError)
async def public_exception_handler(_req: Request, exc: PublicError):
    return JSONResponse(
        content={"message": exc.message, "code": exc.error_code, "status": "error"},
        status_code=exc.http_status,
    )


##


class CacheControlledStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response


app.mount(
    "/uploads/images",
    CacheControlledStaticFiles(directory=IMAGE_UPLOAD_DIR),
    name="images",
)

app.include_router(router)
