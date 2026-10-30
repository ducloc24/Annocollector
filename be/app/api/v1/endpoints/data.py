from typing import Annotated, Any

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    CurrentUser,
    DatasetServiceDep,
    PageParamsDep,
    ProjectAccess,
    ProjectRepositoryDep,
    TaskServiceDep,
    WorkRepositoryDep,
    require_project_permission,
)
from app.core.config import settings
from app.core.exceptions import AppError, ForbiddenError
from app.core.rbac_catalog import Perm
from app.core.storage import UPLOAD_URL_SECONDS, LocalStorage, verify_local_signature
from app.domain.item_types import ITEM_TYPES
from app.domain.label_schema import DEFAULT_TOOL_CALL_SCHEMA, FIELD_TYPES
from app.domain.parsers import PARSERS
from app.schemas.common import Page
from app.schemas.project import (
    DatasetRead,
    DatasetRequest,
    ItemRead,
    ItemTypeRead,
    ParserRead,
    UploadUrlRead,
    UploadUrlRequest,
)
from app.schemas.work import JobConfigDraft, JobConfigRead, JobConfigValidation
from app.services.task import check_job_config

router = APIRouter(tags=["data"])

Member = Annotated[ProjectAccess, require_project_permission(None)]
Uploader = Annotated[ProjectAccess, require_project_permission(Perm.DATASET_UPLOAD)]
Reader = Annotated[ProjectAccess, require_project_permission(Perm.DATASET_READ)]
Deleter = Annotated[ProjectAccess, require_project_permission(Perm.DATASET_DELETE)]
ConfigManager = Annotated[ProjectAccess, require_project_permission(Perm.JOB_CONFIG_MANAGE)]


@router.get("/parsers", response_model=list[ParserRead])
async def list_parsers(_: CurrentUser) -> list[ParserRead]:
    return [
        ParserRead(
            name=p.name,
            version=p.version,
            item_type=p.item_type,
            description=p.description,
            default_options=p.default_options,
        )
        for p in PARSERS.values()
    ]


@router.get("/item-types", response_model=list[ItemTypeRead])
async def list_item_types(_: CurrentUser) -> list[ItemTypeRead]:
    return [
        ItemTypeRead(
            name=t.name,
            description=t.description,
            field_types=list(FIELD_TYPES),
            default_label_schema=DEFAULT_TOOL_CALL_SCHEMA if t.name == "tool_call" else None,
        )
        for t in ITEM_TYPES.values()
    ]


@router.put("/storage/upload", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def local_upload(request: Request, key: str, expires: int, sig: str) -> Response:
    """Receives files when R2 is not configured; the signed URL is the authorization."""
    if settings.r2_configured:
        raise ForbiddenError("Uploads go to R2")
    if not verify_local_signature(key, expires, sig):
        raise ForbiddenError("Upload link is invalid or expired")
    body = await request.body()
    if len(body) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError("File too large", code="file_too_large", status_code=413)
    await LocalStorage().write(key, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- datasets ----------


@router.post("/projects/{project_id}/datasets/upload-url", response_model=UploadUrlRead)
async def upload_url(
    payload: UploadUrlRequest, access: Uploader, datasets: DatasetServiceDep
) -> UploadUrlRead:
    key, url = await datasets.upload_url(access.project_id, payload.filename, payload.size)
    return UploadUrlRead(upload_key=key, url=url, expires_in=UPLOAD_URL_SECONDS)


@router.post("/projects/{project_id}/datasets/preview")
async def preview_dataset(
    payload: DatasetRequest, access: Uploader, datasets: DatasetServiceDep
) -> dict[str, Any]:
    return await datasets.preview(
        access.project_id, payload.upload_key, payload.parser, payload.parser_options
    )


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(
    payload: DatasetRequest, access: Uploader, datasets: DatasetServiceDep
) -> DatasetRead:
    dataset = await datasets.create(
        access.user, access.project_id, payload.upload_key, payload.parser, payload.parser_options
    )
    return DatasetRead.model_validate(dataset)


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetRead])
async def list_datasets(access: Member, repo: ProjectRepositoryDep) -> list[DatasetRead]:
    return [DatasetRead.model_validate(d) for d in await repo.datasets(access.project_id)]


@router.get("/projects/{project_id}/datasets/{version}", response_model=DatasetRead)
async def get_dataset(version: int, access: Member, datasets: DatasetServiceDep) -> DatasetRead:
    return DatasetRead.model_validate(await datasets.get(access.project_id, version))


@router.get("/projects/{project_id}/datasets/{version}/items", response_model=Page[ItemRead])
async def list_items(
    version: int,
    access: Reader,
    datasets: DatasetServiceDep,
    repo: ProjectRepositoryDep,
    page: PageParamsDep,
) -> Page[ItemRead]:
    if "project" not in access.limits:
        # Annotators and reviewers read items only through their jobs.
        raise ForbiddenError("Items are visible through jobs only")
    dataset = await datasets.get(access.project_id, version)
    items, total = await repo.items(dataset.id, page.offset, page.limit)
    return Page[ItemRead](
        items=[ItemRead.model_validate(i) for i in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete("/projects/{project_id}/datasets/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(version: int, access: Deleter, datasets: DatasetServiceDep) -> Response:
    await datasets.delete(access.user, access.project_id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- job configs ----------


@router.post("/projects/{project_id}/job-configs/validate", response_model=JobConfigValidation)
async def validate_job_config(
    payload: JobConfigDraft, access: ConfigManager
) -> JobConfigValidation:
    rules, errors = check_job_config(
        payload.item_type, payload.label_schema, payload.job_rules, payload.self_check
    )
    return JobConfigValidation(valid=not errors, errors=errors, job_rules=rules)


@router.post(
    "/projects/{project_id}/job-configs",
    response_model=JobConfigRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_job_config(
    payload: JobConfigDraft, access: ConfigManager, tasks: TaskServiceDep
) -> JobConfigRead:
    config = await tasks.create_config(
        access.user,
        access.project_id,
        payload.item_type,
        payload.label_schema,
        payload.job_rules,
        payload.self_check,
    )
    return JobConfigRead.model_validate(config)


@router.get("/projects/{project_id}/job-configs", response_model=list[JobConfigRead])
async def list_job_configs(access: Member, work: WorkRepositoryDep) -> list[JobConfigRead]:
    return [JobConfigRead.model_validate(c) for c in await work.job_configs(access.project_id)]


@router.get("/projects/{project_id}/job-configs/{version}", response_model=JobConfigRead)
async def get_job_config(version: int, access: Member, tasks: TaskServiceDep) -> JobConfigRead:
    return JobConfigRead.model_validate(await tasks.config(access.project_id, version))
