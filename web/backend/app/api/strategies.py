from fastapi import APIRouter

from ..services.strategies import list_templates

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("/templates")
def templates():
    return list_templates()
