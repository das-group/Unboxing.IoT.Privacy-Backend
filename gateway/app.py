from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from src.config import ORIGIN
from src.errors import PublicError
from src.routes import router, limiter

app = FastAPI()

## --------------------- Rate Limiting ---------------------- ##

app.state.limiter = limiter

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)

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


# Print routes
print('Printing routes')
for r in app.routes:
    print(r.path, r.name)
print('Printing routes end')