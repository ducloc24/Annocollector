import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.rbac_catalog import Perm
from app.models.user import RefreshToken
from app.services.audit import AuditService
from app.services.authorization import AuthorizationService
from app.services.platform_role import PlatformRoleService
from app.services.user import NewUser, UserService
from tests.fakes import FakeAuditRepo, FakeRbac, FakeTokens, FakeUsers, make_user

NOW = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)


def clock() -> datetime:
    return NOW


@pytest.fixture
def env():
    users, tokens, audit = FakeUsers(), FakeTokens(), FakeAuditRepo()
    rbac = FakeRbac(users)
    audit_service = AuditService(audit)  # type: ignore[arg-type]
    user_service = UserService(users, tokens, rbac, audit_service, clock=clock)  # type: ignore[arg-type]
    role_service = PlatformRoleService(users, rbac, audit_service, clock=clock)  # type: ignore[arg-type]
    authz = AuthorizationService(rbac, clock=clock)  # type: ignore[arg-type]
    hr = users.put(make_user(full_name="HR"))
    rbac.give(hr, "hr_admin")
    return {
        "users": users,
        "tokens": tokens,
        "audit": audit,
        "rbac": rbac,
        "user_service": user_service,
        "role_service": role_service,
        "authz": authz,
        "hr": hr,
    }


# ---------- authorization ----------


async def test_permissions_come_from_active_roles_only(env):
    rbac, authz, users = env["rbac"], env["authz"], env["users"]
    po = users.put(make_user())
    rbac.give(po, "po", expires_at=NOW - timedelta(days=1))
    rbac.give(po, "auditor", revoked_at=NOW - timedelta(days=1))
    assert await authz.limits(po.id, Perm.PROJECT_CREATE) == set()
    assert await authz.limits(po.id, Perm.AUDIT_READ) == set()

    rbac.give(po, "po", expires_at=NOW + timedelta(days=1))
    fresh = AuthorizationService(rbac, clock=clock)  # type: ignore[arg-type]
    assert await fresh.limits(po.id, Perm.PROJECT_CREATE) == {"all"}


async def test_separation_of_duties_at_runtime(env):
    rbac, authz, users = env["rbac"], env["authz"], env["users"]
    admin = users.put(make_user())
    rbac.give(admin, "platform_admin")
    with pytest.raises(ForbiddenError):
        await authz.require(admin.id, Perm.PLATFORM_ROLE_GRANT)
    with pytest.raises(ForbiddenError):
        await authz.require(env["hr"].id, Perm.DATASET_READ)
    assert await authz.require(env["hr"].id, Perm.AUDIT_READ) == {"rbac"}


# ---------- users ----------


async def test_create_user_returns_activation_link_and_audits(env):
    user, link = await env["user_service"].create_user(
        env["hr"], NewUser(email=" Binh@Company.VN", full_name="Bình", employment_type="contractor")
    )
    assert user.email == "binh@company.vn"
    assert not user.is_activated
    assert link.url.startswith("http://localhost:3000/activate?token=")
    assert link.expires_at == NOW + timedelta(hours=72)
    assert env["audit"].actions() == ["user.create"]


async def test_create_user_rejects_duplicates(env):
    service = env["user_service"]
    await service.create_user(
        env["hr"],
        NewUser(email="a@company.vn", full_name="A", employment_type="intern", employee_code="NV1"),
    )
    with pytest.raises(ConflictError) as email:
        await service.create_user(
            env["hr"], NewUser(email="A@company.vn", full_name="B", employment_type="intern")
        )
    assert email.value.code == "email_taken"
    with pytest.raises(ConflictError) as code:
        await service.create_user(
            env["hr"],
            NewUser(
                email="c@company.vn", full_name="C", employment_type="intern", employee_code="NV1"
            ),
        )
    assert code.value.code == "employee_code_taken"


async def test_reissued_activation_link_replaces_the_old_one(env):
    service, tokens = env["user_service"], env["tokens"]
    user, _ = await service.create_user(
        env["hr"], NewUser(email="d@company.vn", full_name="D", employment_type="intern")
    )
    await service.reissue_activation(env["hr"], user.id)
    open_tokens = [t for t in tokens.actions if t.used_at is None]
    assert len(open_tokens) == 1


async def test_disable_user_revokes_everything(env):
    users, rbac, tokens = env["users"], env["rbac"], env["tokens"]
    worker = users.put(make_user())
    rbac.give(worker, "annotator")
    rbac.give(worker, "reviewer")
    tokens.refresh.append(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=worker.id,
            family_id=uuid.uuid4(),
            token_hash="h",
            expires_at=NOW + timedelta(days=1),
        )
    )
    disabled = await env["user_service"].disable_user(env["hr"], worker.id, "left", "Nghỉ việc")
    assert disabled.status == "left"
    assert disabled.left_at == NOW.date()
    assert disabled.token_version == 1
    assert await rbac.active_platform_assignments(worker.id, NOW) == []
    assert all(t.revoked_at == NOW for t in tokens.refresh)
    event = env["audit"].events[-1]
    assert event.action == "user.disable"
    assert sorted(event.before["roles"]) == ["annotator", "reviewer"]


async def test_cannot_disable_self_or_last_hr_admin(env):
    service, users, rbac = env["user_service"], env["users"], env["rbac"]
    with pytest.raises(ForbiddenError):
        await service.disable_user(env["hr"], env["hr"].id, "left", "test")
    other_hr = users.put(make_user())
    with pytest.raises(ConflictError) as last:
        await service.disable_user(other_hr, env["hr"].id, "left", "test")
    assert last.value.code == "last_hr_admin"
    rbac.give(other_hr, "hr_admin")
    await service.disable_user(other_hr, env["hr"].id, "left", "test")


# ---------- platform roles ----------


async def test_grant_role(env):
    users, service = env["users"], env["role_service"]
    worker = users.put(make_user())
    assignment, role = await service.grant(
        env["hr"], worker.id, "annotator", expires_at=NOW + timedelta(days=90)
    )
    assert role.code == "annotator"
    assert assignment.granted_by == env["hr"].id
    assert env["audit"].actions() == ["platform_role.grant"]


async def test_grant_rules(env):
    users, service = env["users"], env["role_service"]
    worker = users.put(make_user())
    with pytest.raises(ForbiddenError) as self_grant:
        await service.grant(env["hr"], env["hr"].id, "po", expires_at=None)
    assert self_grant.value.code == "self_grant_forbidden"
    with pytest.raises(NotFoundError):
        await service.grant(env["hr"], worker.id, "owner", expires_at=None)
    with pytest.raises(AppError) as past:
        await service.grant(env["hr"], worker.id, "po", expires_at=NOW - timedelta(seconds=1))
    assert past.value.code == "invalid_expiry"
    await service.grant(env["hr"], worker.id, "po", expires_at=None)
    with pytest.raises(ConflictError) as dup:
        await service.grant(env["hr"], worker.id, "po", expires_at=None)
    assert dup.value.code == "role_already_granted"


async def test_conflict_warning_needs_acknowledgement(env):
    users, service = env["users"], env["role_service"]
    admin = users.put(make_user())
    await service.grant(env["hr"], admin.id, "platform_admin", expires_at=None)
    with pytest.raises(ConflictError) as warn:
        await service.grant(env["hr"], admin.id, "hr_admin", expires_at=None)
    assert warn.value.code == "role_conflict_warning"
    await service.grant(env["hr"], admin.id, "hr_admin", expires_at=None, acknowledge_warning=True)


async def test_grant_to_disabled_user_is_rejected(env):
    worker = env["users"].put(make_user(status="suspended"))
    with pytest.raises(ConflictError) as exc:
        await env["role_service"].grant(env["hr"], worker.id, "po", expires_at=None)
    assert exc.value.code == "account_inactive"


async def test_revoke_and_extend(env):
    users, service, rbac = env["users"], env["role_service"], env["rbac"]
    worker = users.put(make_user())
    assignment, _ = await service.grant(env["hr"], worker.id, "reviewer", expires_at=None)
    await service.extend(env["hr"], worker.id, assignment.id, NOW + timedelta(days=30))
    assert assignment.expires_at == NOW + timedelta(days=30)
    await service.revoke(env["hr"], worker.id, assignment.id, "Hết hợp đồng")
    assert await rbac.active_platform_assignments(worker.id, NOW) == []
    with pytest.raises(NotFoundError):
        await service.revoke(env["hr"], worker.id, assignment.id, "again")


async def test_cannot_revoke_last_hr_admin(env):
    rbac, service, users = env["rbac"], env["role_service"], env["users"]
    hr_assignment = rbac.assignments[0]
    other = users.put(make_user())
    with pytest.raises(ConflictError) as exc:
        await service.revoke(other, env["hr"].id, hr_assignment.id, "test")
    assert exc.value.code == "last_hr_admin"


async def test_expiring_roles(env):
    users, rbac, service = env["users"], env["rbac"], env["role_service"]
    worker = users.put(make_user())
    rbac.give(worker, "annotator", expires_at=NOW + timedelta(days=5))
    rbac.give(worker, "reviewer", expires_at=NOW + timedelta(days=60))

    async def expiring_assignments(now, until):
        rows = []
        for a, r in await rbac.active_platform_assignments(worker.id, now):
            if a.expires_at and now < a.expires_at <= until:
                rows.append((a, r, worker))
        return rows

    rbac.expiring_assignments = expiring_assignments
    rows = await service.expiring(30)
    assert [r.code for _, r, _ in rows] == ["annotator"]
