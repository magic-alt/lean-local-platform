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
    market: str = "usa"
    parameters: dict | None = None


class FileWrite(BaseModel):
    path: str
    content: str


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
            market=request.market,
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
def delete_project(project_id: str):
    try:
        return {"deleted": True, "details": project_service.delete_project(project_id)}
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
