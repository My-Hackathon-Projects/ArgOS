from fastapi import APIRouter

from app.api.routes import apply, hello

api_router = APIRouter()
api_router.include_router(hello.router)
api_router.include_router(apply.router)
