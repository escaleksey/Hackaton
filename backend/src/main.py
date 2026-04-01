from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.presentation.api.routes.contracts import router as contracts_router

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
