import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import AppError, UnauthorizedError
from app.core.security import hash_opaque_token, hash_password
from app.models.user import UserActionToken, UserStatus
from app.services.audit import AuditService
from app.services.auth import AuthService
from tests.fakes import FakeAuditRepo, FakeTokens, FakeUsers, make_user

PASSWORD = "a-strong-password"


class Clock:
    def __init__(self) -> None:
        # Starts at the real time: access tokens are decoded against the wall clock.
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def env():
    users, tokens, audit = FakeUsers(), FakeTokens(), FakeAuditRepo()
    clock = Clock()
    service = AuthService(users, tokens, AuditService(audit), clock=clock)  # type: ignore[arg-type]
    user = users.put(make_user(email="an@company.vn", password_hash=hash_password(PASSWORD)))
    return service, users, tokens, audit, clock, user


async def login(service):
    return await service.login("An@Company.vn ", PASSWORD, ip="1.2.3.4", user_agent="pytest")


async def test_login_returns_working_access_token(env):
    service, _, _, _, _, user = env
    issued = await login(service)
    assert (await service.authenticate(issued.access_token)).id == user.id


async def test_wrong_password_and_unknown_email_give_the_same_error(env):
    service = env[0]
    with pytest.raises(UnauthorizedError) as wrong:
        await service.login("an@company.vn", "nope", ip=None, user_agent=None)
    with pytest.raises(UnauthorizedError) as unknown:
        await service.login("ghost@company.vn", PASSWORD, ip=None, user_agent=None)
    assert wrong.value.code == unknown.value.code == "invalid_credentials"
    assert wrong.value.message == unknown.value.message


async def test_not_activated_user_cannot_login(env):
    service, users = env[0], env[1]
    users.put(make_user(email="new@company.vn", password_hash=None))
    with pytest.raises(UnauthorizedError) as exc:
        await service.login("new@company.vn", PASSWORD, ip=None, user_agent=None)
    assert exc.value.code == "invalid_credentials"


async def test_suspended_user_cannot_login(env):
    service, _, _, _, _, user = env
    user.status = UserStatus.SUSPENDED
    with pytest.raises(UnauthorizedError) as exc:
        await login(service)
    assert exc.value.code == "account_inactive"


async def test_bumped_token_version_revokes_access_token(env):
    service, _, _, _, _, user = env
    issued = await login(service)
    user.token_version += 1
    with pytest.raises(UnauthorizedError) as exc:
        await service.authenticate(issued.access_token)
    assert exc.value.code == "token_revoked"


async def test_disabled_user_access_token_is_revoked(env):
    service, _, _, _, _, user = env
    issued = await login(service)
    user.status = UserStatus.LEFT
    with pytest.raises(UnauthorizedError) as exc:
        await service.authenticate(issued.access_token)
    assert exc.value.code == "token_revoked"


async def test_refresh_rotates_token(env):
    service, _, tokens, _, _, _ = env
    first = await login(service)
    second = await service.refresh(first.refresh_token, ip=None, user_agent=None)
    assert second.refresh_token != first.refresh_token
    old = await tokens.get_refresh_by_hash(hash_opaque_token(first.refresh_token))
    new = await tokens.get_refresh_by_hash(hash_opaque_token(second.refresh_token))
    assert old.revoked_at is not None and old.replaced_by_id == new.id
    assert old.family_id == new.family_id


async def test_reusing_rotated_refresh_token_revokes_whole_family(env):
    service, _, tokens, _, _, _ = env
    first = await login(service)
    second = await service.refresh(first.refresh_token, ip=None, user_agent=None)
    with pytest.raises(UnauthorizedError) as exc:
        await service.refresh(first.refresh_token, ip=None, user_agent=None)
    assert exc.value.code == "token_revoked"
    with pytest.raises(UnauthorizedError):
        await service.refresh(second.refresh_token, ip=None, user_agent=None)
    assert all(t.revoked_at is not None for t in tokens.refresh)


async def test_expired_refresh_token(env):
    service, _, _, _, clock, _ = env
    issued = await login(service)
    clock.now += timedelta(days=8)
    with pytest.raises(UnauthorizedError) as exc:
        await service.refresh(issued.refresh_token, ip=None, user_agent=None)
    assert exc.value.code == "token_expired"


async def test_refresh_for_disabled_user_is_rejected(env):
    service, _, _, _, _, user = env
    issued = await login(service)
    user.status = UserStatus.SUSPENDED
    with pytest.raises(UnauthorizedError) as exc:
        await service.refresh(issued.refresh_token, ip=None, user_agent=None)
    assert exc.value.code == "token_revoked"


async def test_logout_revokes_refresh_token(env):
    service = env[0]
    issued = await login(service)
    await service.logout(issued.refresh_token)
    with pytest.raises(UnauthorizedError):
        await service.refresh(issued.refresh_token, ip=None, user_agent=None)


def activation_token(user, clock, raw="raw-activation-token", **overrides):
    values = {
        "id": uuid.uuid4(),
        "user_id": user.id,
        "purpose": "activate",
        "token_hash": hash_opaque_token(raw),
        "expires_at": clock.now + timedelta(hours=72),
    }
    values.update(overrides)
    return UserActionToken(**values)


async def test_activate_sets_password_once(env):
    service, users, tokens, audit, clock, _ = env
    user = users.put(make_user(email="new@company.vn", password_hash=None))
    tokens.actions.append(activation_token(user, clock))
    await service.activate("raw-activation-token", "new-strong-password")
    assert user.is_activated
    assert "user.activate" in audit.actions()
    with pytest.raises(AppError) as exc:
        await service.activate("raw-activation-token", "another-password!")
    assert exc.value.code == "invalid_action_token"


async def test_activate_rejects_expired_link_and_weak_password(env):
    service, users, tokens, _, clock, _ = env
    user = users.put(make_user(password_hash=None))
    tokens.actions.append(
        activation_token(user, clock, raw="expired-token-x", expires_at=clock.now)
    )
    with pytest.raises(AppError) as expired:
        await service.activate("expired-token-x", "new-strong-password")
    assert expired.value.code == "invalid_action_token"

    tokens.actions.append(activation_token(user, clock, raw="fresh-token-xyz"))
    with pytest.raises(AppError) as weak:
        await service.activate("fresh-token-xyz", "short")
    assert weak.value.code == "password_too_weak"


async def test_change_password_signs_out_other_sessions(env):
    service, _, tokens, _, _, user = env
    other = await login(service)
    issued = await service.change_password(
        user, PASSWORD, "brand-new-password", ip=None, user_agent=None
    )
    with pytest.raises(UnauthorizedError):
        await service.authenticate(other.access_token)
    with pytest.raises(UnauthorizedError):
        await service.refresh(other.refresh_token, ip=None, user_agent=None)
    assert (await service.authenticate(issued.access_token)).id == user.id


async def test_change_password_requires_current_password(env):
    service, _, _, _, _, user = env
    with pytest.raises(UnauthorizedError):
        await service.change_password(user, "wrong", "brand-new-password", ip=None, user_agent=None)
