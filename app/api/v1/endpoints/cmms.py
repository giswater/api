"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, File, Query
from fastapi.responses import FileResponse

from app.api.deps import CommonsDep, get_service_context
from app.core.config import global_settings
from app.schemas.cmms.cmms_models import AttachmentUpdate, AttachmentUpload, CmmsResponse, VisitCreate, VisitUpdate
from app.services.cmms_service import CmmsService

router = APIRouter(prefix="/cmms", tags=["CMMS"])


def _service(commons: dict) -> CmmsService:
    return CmmsService(
        get_service_context(commons),
        storage_dir=Path(global_settings.cmms_storage_dir),
        max_upload_bytes=commons["tenant"].settings.cmms_max_upload_mb * 1024 * 1024,
    )


def _file(stored) -> FileResponse:
    path, media_type, filename = stored
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/visits", response_model=CmmsResponse, response_model_exclude_unset=True)
async def list_visits(
    commons: CommonsDep,
    sys_code: Optional[str] = Query(None, alias="sysCode", description="Feature sys_code"),
    visit_type: Optional[str] = Query(None, alias="type", description="Visit type"),
    status: Optional[str] = Query(None, description="Visit status"),
    limit: int = Query(100, ge=1, le=1000),
):
    return await _service(commons).list_visits(sys_code=sys_code, visit_type=visit_type, status=status, limit=limit)


@router.get("/visits/{visit_id}", response_model=CmmsResponse, response_model_exclude_unset=True)
async def get_visit(commons: CommonsDep, visit_id: UUID):
    return await _service(commons).get_visit(visit_id)


@router.post("/visits", response_model=CmmsResponse, response_model_exclude_unset=True)
async def create_visit(commons: CommonsDep, visit: VisitCreate):
    return await _service(commons).create_visit(visit)


@router.patch("/visits/{visit_id}", response_model=CmmsResponse, response_model_exclude_unset=True)
async def update_visit(commons: CommonsDep, visit_id: UUID, visit: VisitUpdate):
    return await _service(commons).update_visit(visit_id, visit)


@router.delete("/visits/{visit_id}", response_model=CmmsResponse, response_model_exclude_unset=True)
async def delete_visit(commons: CommonsDep, visit_id: UUID):
    return await _service(commons).delete_visit(visit_id)


@router.get("/visits/{visit_id}/attachments", response_model=CmmsResponse, response_model_exclude_unset=True)
async def list_visit_attachments(
    commons: CommonsDep,
    visit_id: UUID,
    limit: int = Query(100, ge=1, le=1000),
):
    return await _service(commons).list_attachments(visit_id=visit_id, limit=limit)


@router.post(
    "/visits/{visit_id}/attachments",
    response_model=CmmsResponse,
    response_model_exclude_unset=True,
)
async def add_visit_attachment(
    commons: CommonsDep,
    visit_id: UUID,
    upload: Annotated[AttachmentUpload, File()],
):
    return await _service(commons).add_attachment(upload, visit_id=visit_id)


@router.get("/visits/{visit_id}/attachments/{attachment_id}/file")
async def get_visit_attachment_file(
    commons: CommonsDep,
    visit_id: UUID,
    attachment_id: UUID,
    thumbnail: bool = Query(False),
):
    stored = await _service(commons).get_file(attachment_id, visit_id=visit_id, thumbnail=thumbnail)
    return _file(stored)


@router.get("/attachments", response_model=CmmsResponse, response_model_exclude_unset=True)
async def list_attachments(
    commons: CommonsDep,
    sys_code: Optional[str] = Query(None, alias="sysCode"),
    visit_id: Optional[UUID] = Query(None, alias="visitId"),
    limit: int = Query(100, ge=1, le=1000),
):
    return await _service(commons).list_attachments(sys_code=sys_code, visit_id=visit_id, limit=limit)


@router.post("/attachments", response_model=CmmsResponse, response_model_exclude_unset=True)
async def upload_attachment(commons: CommonsDep, upload: Annotated[AttachmentUpload, File()]):
    return await _service(commons).add_attachment(upload)


@router.get("/attachments/{attachment_id}", response_model=CmmsResponse, response_model_exclude_unset=True)
async def get_attachment(commons: CommonsDep, attachment_id: UUID):
    return await _service(commons).get_attachment(attachment_id)


@router.get("/attachments/{attachment_id}/file")
async def get_attachment_file(
    commons: CommonsDep,
    attachment_id: UUID,
    thumbnail: bool = Query(False),
):
    stored = await _service(commons).get_file(attachment_id, thumbnail=thumbnail)
    return _file(stored)


@router.patch("/attachments/{attachment_id}", response_model=CmmsResponse, response_model_exclude_unset=True)
async def update_attachment(commons: CommonsDep, attachment_id: UUID, attachment: AttachmentUpdate):
    return await _service(commons).update_attachment(attachment_id, attachment)


@router.delete("/attachments/{attachment_id}", response_model=CmmsResponse, response_model_exclude_unset=True)
async def delete_attachment(commons: CommonsDep, attachment_id: UUID):
    return await _service(commons).delete_attachment(attachment_id)
