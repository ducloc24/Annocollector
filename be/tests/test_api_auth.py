"""HTTP-level checks with services overridden, so no database is needed."""

import uuid

from app.api.deps import get_auth_service, get_authorization_service
from app.core.exceptions import UnauthorizedError
from app.core.rbac_catalog import Perm
from app.main import app
from app.services.authorization import AuthorizationService
from tests.fakes import FakeRbac, FakeUsers, make_user


class StubAuth:
    def __init__(self, user):
        self.user = user

    async def authenticate(self, token: str):
        if token != "good":
            raise UnauthorizedError("Invalid access token")
        return self.user


def override(user, rbac):
    app.dependency_overrides[get_auth_service] = lambda: StubAuth(user)
    app.dependency_overrides[get_authorization_service] = lambda: AuthorizationService(rbac)


async def test_missing_token_is_401(client):
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_user_without_permission_gets_403(client):
    users = FakeUsers()
    rbac = FakeRbac(users)
    worker = users.put(make_user())
    rbac.give(worker, "annotator")
    override(worker, rbac)
    try:
        response = await client.get("/api/v1/users", headers={"Authorization": "Bearer good"})
        assert response.status_code == 403
        assert response.json()["details"] == {"permission": Perm.USER_MANAGE}

        response = await client.post(
            f"/api/v1/users/{uuid.uuid4()}/platform-roles",
            json={"role": "po"},
            headers={"Authorization": "Bearer good"},
        )
        assert response.status_code == 403

        response = await client.get(
            "/api/v1/audit-events", headers={"Authorization": "Bearer good"}
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


async def test_bad_token_is_401(client):
    users = FakeUsers()
    override(users.put(make_user()), FakeRbac(users))
    try:
        response = await client.get("/api/v1/me", headers={"Authorization": "Bearer bad"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


async def test_my_permissions(client):
    users = FakeUsers()
    rbac = FakeRbac(users)
    hr = users.put(make_user())
    rbac.give(hr, "hr_admin")
    override(hr, rbac)
    try:
        response = await client.get(
            "/api/v1/me/permissions", headers={"Authorization": "Bearer good"}
        )
        assert response.status_code == 200
        permissions = response.json()["permissions"]
        assert permissions["user.manage"] == ["all"]
        assert permissions["audit.read"] == ["rbac"]
        assert "dataset.read" not in permissions
    finally:
        app.dependency_overrides.clear()


async def test_login_validation_error_is_422(client):
    response = await client.post("/api/v1/auth/login", json={"email": "x"})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
