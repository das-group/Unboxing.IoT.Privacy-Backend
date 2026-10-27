from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from src.processing import (
    start_processing_pool,
    stop_processing_pool,
)
from src.routes import router


@asynccontextmanager
async def lifetime(_app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    start_processing_pool(max_workers=1)

    yield

    # shutdown

    stop_processing_pool(wait=True)


app = FastAPI(lifespan=lifetime)


app.include_router(router)
