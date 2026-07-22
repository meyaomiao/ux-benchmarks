from fastapi import APIRouter
from app.api.v1 import m0, m1, m2, m3, m4, m5, l5

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(m0.router)
api_router.include_router(m1.router)
api_router.include_router(m2.router)
api_router.include_router(m3.router)
api_router.include_router(m4.router)
api_router.include_router(m5.router)
api_router.include_router(l5.router)
