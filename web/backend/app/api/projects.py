from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from ..core.errors import LeanWebError, NotFoundError
from ..services import projects as project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    language: str = "Python"
    algorithmClass: str | None = None
    templateKey: str | None = None
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    parameters: dict | None = None


class FileWrite(BaseModel):
    path: str
    content: str


class ProjectUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None


class ProjectClone(BaseModel):
    name: str | None = None
    config: dict | None = None


@router.get("")
def list_projects():
    return project_service.list_projects()


@router.post("")
def create_project(request: ProjectCreate):
    try:
        return project_service.create_project(
            request.name,
            request.language,
            request.algorithmClass,
            template_key=request.templateKey,
            asset_class=request.assetClass,
            market=request.market,
            venue=request.venue,
            resolution=request.resolution,
            data_type=request.dataType,
            parameters=request.parameters,
        )
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}")
def get_project(project_id: str):
    try:
        return project_service.get_project(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_id}")
@router.delete("/{project_id}/")
def delete_project(project_id: str):
    try:
        return {"deleted": True, "details": project_service.delete_project(project_id)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{project_id}")
def update_project(project_id: str, request: ProjectUpdate):
    try:
        return project_service.update_project(
            project_id,
            name=request.name,
            config_updates=request.config,
        )
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/clone")
def clone_project(project_id: str, request: ProjectClone):
    try:
        return project_service.clone_project(
            project_id,
            name=request.name,
            config_updates=request.config,
        )
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/files")
def file_tree(project_id: str):
    try:
        return project_service.file_tree(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/file")
def read_file(project_id: str, path: str):
    try:
        return project_service.read_file(project_id, path)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{project_id}/file")
def write_file(project_id: str, request: FileWrite):
    try:
        return project_service.write_file(project_id, request.path, request.content)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
