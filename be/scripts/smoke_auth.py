"""Smoke test for build step 1 against a running API and the real database.

    SMOKE_HR_EMAIL=... SMOKE_HR_PASSWORD=... uv run python scripts/smoke_auth.py

Creates one throwaway user (smoke-<timestamp>@example.invalid) and offboards it at the
end. Users are never hard-deleted, so the record stays with status "left".
"""

import os
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000/api/v1")
HR_EMAIL = os.environ["SMOKE_HR_EMAIL"]
HR_PASSWORD = os.environ["SMOKE_HR_PASSWORD"]

passed = 0


def check(label: str, response: httpx.Response, status: int, code: str | None = None) -> Any:
    global passed
    body = response.json() if response.content else {}
    body_code = body.get("code", "") if isinstance(body, dict) else ""
    ok = response.status_code == status and (code is None or body_code == code)
    mark = "OK " if ok else "FAIL"
    print(f"[{mark}] {label}: {response.status_code} {body_code}".rstrip())
    if not ok:
        print(f"       expected {status} {code or ''}; body={body}")
        sys.exit(1)
    passed += 1
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refresh_cookie(response: httpx.Response) -> str:
    # The cookie is Secure; httpx will not send it back over http, so pass it by hand.
    value = response.cookies.get("refresh_token")
    assert value, "refresh_token cookie missing"
    return value


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        check("health", api.get("/health"), 200)
        check("no token -> 401", api.get("/me"), 401, "unauthorized")
        check(
            "wrong password -> 401",
            api.post("/auth/login", json={"email": HR_EMAIL, "password": "wrong-password"}),
            401,
            "invalid_credentials",
        )

        login = api.post("/auth/login", json={"email": HR_EMAIL, "password": HR_PASSWORD})
        hr = check("hr login", login, 200)
        hr_token = hr["access_token"]
        me = check("hr /me", api.get("/me", headers=bearer(hr_token)), 200)
        assert "hr_admin" in [r["role"] for r in me["platform_roles"]], me

        perms = check(
            "hr /me/permissions", api.get("/me/permissions", headers=bearer(hr_token)), 200
        )
        assert "dataset.read" not in perms["permissions"], perms
        check("roles catalog", api.get("/roles", headers=bearer(hr_token)), 200)

        email = f"smoke-{int(time.time())}@example.invalid"
        created = check(
            "create user",
            api.post(
                "/users",
                json={"email": email, "full_name": "Smoke Test", "employment_type": "contractor"},
                headers=bearer(hr_token),
            ),
            201,
        )
        user_id = created["user"]["id"]
        token = parse_qs(urlparse(created["activation_url"]).query)["token"][0]
        check(
            "duplicate email -> 409",
            api.post(
                "/users",
                json={"email": email, "full_name": "Again", "employment_type": "intern"},
                headers=bearer(hr_token),
            ),
            409,
            "email_taken",
        )

        check(
            "login before activation -> 401",
            api.post("/auth/login", json={"email": email, "password": "smoke-password-1"}),
            401,
            "invalid_credentials",
        )
        check(
            "weak password -> 400",
            api.post("/auth/activate", json={"token": token, "password": "short"}),
            400,
            "password_too_weak",
        )
        check(
            "activate",
            api.post("/auth/activate", json={"token": token, "password": "smoke-password-1"}),
            204,
        )
        check(
            "activation link reused -> 400",
            api.post("/auth/activate", json={"token": token, "password": "smoke-password-2"}),
            400,
            "invalid_action_token",
        )

        user_login = api.post("/auth/login", json={"email": email, "password": "smoke-password-1"})
        user_body = check("user login", user_login, 200)
        user_token = user_body["access_token"]
        user_refresh = refresh_cookie(user_login)
        check("user /me", api.get("/me", headers=bearer(user_token)), 200)
        check(
            "user lists users -> 403",
            api.get("/users", headers=bearer(user_token)),
            403,
            "forbidden",
        )

        grant = check(
            "grant annotator",
            api.post(
                f"/users/{user_id}/platform-roles",
                json={"role": "annotator"},
                headers=bearer(hr_token),
            ),
            201,
        )
        check(
            "grant twice -> 409",
            api.post(
                f"/users/{user_id}/platform-roles",
                json={"role": "annotator"},
                headers=bearer(hr_token),
            ),
            409,
            "role_already_granted",
        )
        me = check("user /me after grant", api.get("/me", headers=bearer(user_token)), 200)
        assert [r["role"] for r in me["platform_roles"]] == ["annotator"], me

        rotated = api.post("/auth/refresh", cookies={"refresh_token": user_refresh})
        check("refresh rotates", rotated, 200)
        check(
            "old refresh token reused -> 401",
            api.post("/auth/refresh", cookies={"refresh_token": user_refresh}),
            401,
            "token_revoked",
        )

        check(
            "revoke annotator",
            api.request(
                "DELETE",
                f"/users/{user_id}/platform-roles/{grant['id']}",
                json={"reason": "smoke test"},
                headers=bearer(hr_token),
            ),
            204,
        )
        check(
            "disable user",
            api.post(
                f"/users/{user_id}/disable",
                json={"status": "left", "reason": "smoke test cleanup"},
                headers=bearer(hr_token),
            ),
            200,
        )
        check(
            "disabled user's access token -> 401",
            api.get("/me", headers=bearer(user_token)),
            401,
            "token_revoked",
        )
        check(
            "disabled user login -> 401",
            api.post("/auth/login", json={"email": email, "password": "smoke-password-1"}),
            401,
            "account_inactive",
        )

        audit = check(
            "audit log",
            api.get("/audit-events", params={"target_id": user_id}, headers=bearer(hr_token)),
            200,
        )
        actions = {e["action"] for e in audit["items"]}
        assert {"user.create", "user.activate", "user.disable"} <= actions, actions

        check(
            "hr logout",
            api.post("/auth/logout", cookies={"refresh_token": refresh_cookie(login)}),
            204,
        )

    print(f"\nAll {passed} checks passed. Test user {email} is left with status 'left'.")


if __name__ == "__main__":
    main()
