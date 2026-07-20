from fastapi import APIRouter, HTTPException

from ..core.errors import NotFoundError
from ..services import help_docs


router = APIRouter(prefix="/api/help", tags=["help"])


@router.get("/articles")
def articles(q: str | None = None):
    items = help_docs.list_articles(q)
    return {"items": items, "count": len(items)}


@router.get("/articles/{slug}")
def article(slug: str):
    try:
        return help_docs.article(slug)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
