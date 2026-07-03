from fastapi import APIRouter

from ..services.data import djia_universe

router = APIRouter(prefix="/api/universes", tags=["universes"])


@router.get("/djia")
def djia():
    return djia_universe()
