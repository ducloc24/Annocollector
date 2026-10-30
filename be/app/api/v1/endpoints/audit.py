import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import AuditServiceDep, AuthorizationDep, CurrentUser, PageParamsDep
from app.core.rbac_catalog import Limit, Perm
from app.schemas.audit import AuditEventRead
from app.schemas.common import Page

router = APIRouter(tags=["audit"])


@router.get("/audit-events", response_model=Page[AuditEventRead], summary="Read the audit log")
async def list_audit_events(
    user: CurrentUser,
    authz: AuthorizationDep,
    audit: AuditServiceDep,
    page: PageParamsDep,
    actor_id: uuid.UUID | None = None,
    action: str | None = Query(None, max_length=64),
    target_type: str | None = Query(None, max_length=64),
    target_id: str | None = Query(None, max_length=64),
    project_id: uuid.UUID | None = None,
    since: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    until: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> Page[AuditEventRead]:
    limits = await authz.require(user.id, Perm.AUDIT_READ)
    events, total = await audit.search(
        # hr_admin only reads access-control events unless another role grants more.
        access_control_only=Limit.ALL not in limits,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        since=since,
        until=until,
        offset=page.offset,
        limit=page.limit,
    )
    return Page[AuditEventRead](
        items=[AuditEventRead.model_validate(e) for e in events],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
