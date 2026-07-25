from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin
from app.api.v1.router import api_router
from app.core.errors import register_exception_handlers

app = FastAPI(
    title="UX Benchmarks",
    version="0.1.0",
    description="场景级 UX 设计标杆工具 · 采集阶段 API",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)
app.include_router(admin.router)


@app.get("/healthz", tags=["Health"])
def healthz():
    return {"status": "ok", "version": "0.1.0"}
