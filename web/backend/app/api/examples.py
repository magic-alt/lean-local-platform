from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.errors import NotFoundError
from ..services import examples


router = APIRouter(prefix="/api/examples", tags=["examples"])

_RETIRED_RESEARCH_EXAMPLE_DETAIL = (
    "Research examples are retired from the public platform surface; use qlib-platform."
)


class ExampleInstantiateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    overrides: dict[str, Any] = Field(default_factory=dict)


def _is_research(kind: str | None) -> bool:
    return str(kind or "").strip().lower() == "research"


@router.get("")
def catalog(kind: str | None = None, q: str | None = None):
    if _is_research(kind):
        return {"items": [], "count": 0}
    items = [item for item in examples.list_examples(kind, q) if item.get("kind") != "research"]
    return {"items": items, "count": len(items)}


@router.get("/{kind}/{key}")
def detail(kind: str, key: str):
    if _is_research(kind):
        raise HTTPException(status_code=404, detail=_RETIRED_RESEARCH_EXAMPLE_DETAIL)
    try:
        return examples.get_example(kind, key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{kind}/{key}/instantiate")
def instantiate(kind: str, key: str, request: ExampleInstantiateRequest):
    if _is_research(kind):
        raise HTTPException(status_code=404, detail=_RETIRED_RESEARCH_EXAMPLE_DETAIL)
    try:
        return examples.instantiate_example(kind, key, name=request.name, overrides=request.overrides)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
