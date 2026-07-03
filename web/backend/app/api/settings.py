from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ..services.settings import get_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")


@router.get("")
def read_settings():
    return get_settings()


@router.put("")
def save_settings(request: SettingsUpdate):
    updates: dict[str, Any] = request.model_dump()
    updates.update(request.model_extra or {})
    return update_settings(updates)
