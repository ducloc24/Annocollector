from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import PageParamsDep
from app.core.exceptions import (
    ForbiddenError,
    InvalidStateError,
    UnauthorizedError,
    register_exception_handlers,
)
from app.core.request_context import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    get_request_context,
)


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    router = APIRouter()

    @router.get("/unauthorized")
    async def unauthorized() -> None:
        raise UnauthorizedError("Missing token")

    @router.get("/forbidden")
    async def forbidden() -> None:
        raise ForbiddenError("No permission")

    @router.get("/invalid-state")
    async def invalid_state() -> None:
        raise InvalidStateError(
            "Cannot submit",
            details={"from": "assigned", "to": "submitted", "allowed": ["in_progress"]},
        )

    @router.get("/context")
    async def context() -> dict[str, str | None]:
        ctx = get_request_context()
        assert ctx is not None
        return {"request_id": ctx.request_id, "user_agent": ctx.user_agent}

    @router.get("/page")
    async def page(params: PageParamsDep) -> dict[str, int]:
        return {"offset": params.offset, "limit": params.limit}

    app.include_router(router)
    return app


async def call(path: str, headers: dict[str, str] | None = None):
    transport = ASGITransport(app=build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert response.headers[REQUEST_ID_HEADER]


async def test_sample_items_endpoint_removed(client):
    response = await client.get("/api/v1/items")
    assert response.status_code == 404


async def test_error_codes_and_statuses():
    response = await call("/unauthorized")
    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized", "message": "Missing token"}

    response = await call("/forbidden")
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_error_details_are_returned():
    response = await call("/invalid-state")
    assert response.status_code == 409
    assert response.json() == {
        "code": "invalid_state",
        "message": "Cannot submit",
        "details": {"from": "assigned", "to": "submitted", "allowed": ["in_progress"]},
    }


async def test_request_id_is_generated_and_exposed():
    response = await call("/context", headers={"User-Agent": "pytest"})
    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 32
    assert response.json() == {"request_id": request_id, "user_agent": "pytest"}


async def test_valid_incoming_request_id_is_kept():
    response = await call("/context", headers={REQUEST_ID_HEADER: "abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


async def test_unsafe_incoming_request_id_is_replaced():
    response = await call("/context", headers={REQUEST_ID_HEADER: "bad id <script>"})
    assert response.headers[REQUEST_ID_HEADER] != "bad id <script>"
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


async def test_page_params_defaults_and_limits():
    assert (await call("/page")).json() == {"offset": 0, "limit": 20}
    assert (await call("/page?offset=40&limit=100")).json() == {"offset": 40, "limit": 100}
    assert (await call("/page?limit=101")).status_code == 422
    assert (await call("/page?offset=-1")).status_code == 422
