from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.concurrency import asynccontextmanager

import asyncio
from typing import AsyncGenerator
from pathlib import Path

from src.routes import router
from src.errors import PublicError
from src.processing import start_processing_pool, stop_processing_pool
from src.cleanup import cleanup_old_files


from src.config import UPLOADS_DIR, CACHE_DIR

Path(UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

## --------------------- FastAPI Application Lifespan --------------------- ##


@asynccontextmanager
async def lifetime(_app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    start_processing_pool(max_workers=1)

    cleanup_task = asyncio.create_task(cleanup_old_files())

    yield

    # shutdown

    stop_processing_pool(wait=True)

    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifetime)


##--------------------- Global Exception Handlers --------------------- ##


@app.exception_handler(PublicError)
async def public_exception_handler(_req: Request, exc: PublicError):
    return JSONResponse(
        content={"message": exc.message, "code": exc.error_code, "status": "error"},
        status_code=exc.http_status,
    )


app.include_router(router)
