import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.presentation.api.routes.contracts import router as contracts_router

LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="Contract Correction Service",
    version="0.1.0",
    description="API for uploading, correcting, and downloading contract drafts.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contracts_router)


@app.get("/health", tags=["health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error_id = str(uuid4())
    LOGGER.exception(
        "Unhandled backend exception",
        extra={
            "error_id": error_id,
            "method": request.method,
            "path": str(request.url.path),
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Internal Server Error. "
                f"error_id={error_id}. "
                "Проверьте логи backend для точной причины."
            )
        },
    )
