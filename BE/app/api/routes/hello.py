from fastapi import APIRouter

router = APIRouter(tags=["hello"])


@router.get("/")
async def hello_world() -> dict[str, str]:
    return {"msg": "Hello World"}


@router.get("/health-check/")
async def health_check() -> bool:
    return True
