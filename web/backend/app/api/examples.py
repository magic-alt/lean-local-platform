from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.errors import NotFoundError
from ..services import examples


router = APIRouter(prefix="/api/examples", tags=["examples"])


class ExampleInstantiateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    overrides: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def catalog(kind: str | None = None, q: str | None = None):
    items = examples.list_examples(kind, q)
    return {"items": items, "count": len(items)}


@router.get("/{kind}/{key}")
def detail(kind: str, key: str):
    try:
        return examples.get_example(kind, key)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{kind}/{key}/instantiate")
def instantiate(kind: str, key: str, request: ExampleInstantiateRequest):
    try:
        return examples.instantiate_example(kind, key, name=request.name, overrides=request.overrides)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
