from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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


@router.get("/assets/{asset_path:path}", include_in_schema=False)
def asset(asset_path: str):
    try:
        path = help_docs.asset(asset_path)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})
