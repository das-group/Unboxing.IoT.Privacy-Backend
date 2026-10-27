from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from src.routes import router
from src.processing import (
    start_processing_pool,
    stop_processing_pool
)

@asynccontextmanager
async def lifetime(_app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    start_processing_pool(max_workers=2)
   

    yield

    # shutdown
    stop_processing_pool(wait=True)


app = FastAPI(lifespan=lifetime)


app.include_router(router)
