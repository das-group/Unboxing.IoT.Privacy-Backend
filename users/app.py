from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from src.config import ORIGIN
from src.db_users import initialize_db
from src.errors import PublicError
from src.routes import router

## --------------------- FastAPI Application Lifespan --------------------- ##


@asynccontextmanager
async def startup_event(_app: FastAPI) -> AsyncGenerator[None, None]:
    await initialize_db()

    yield


app = FastAPI(lifespan=startup_event)

## --------------------- CORS Middleware --------------------- ##
origins = ORIGIN


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

##--------------------- Global Exception Handlers --------------------- ##


@app.exception_handler(PublicError)
async def public_exception_handler(_req: Request, exc: PublicError):
    return JSONResponse(
        content={"message": exc.message, "code": exc.error_code, "status": "error"},
        status_code=exc.http_status,
    )


## --------------------- Mount Static Files & Include Routers --------------------- ##

app.mount("/index", StaticFiles(directory="templates", html=True), name="static")


app.include_router(router)
