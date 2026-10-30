"""End-to-end smoke test of the whole labelling flow against a running API.

    SMOKE_HR_EMAIL=... SMOKE_HR_PASSWORD=... uv run python scripts/smoke_flow.py

HR creates a PO, an annotator and a reviewer plus a team; the PO sets up a project from
samples/trajectories.jsonl; the annotator and reviewer work every job (one goes through a
reject/rework round); the PO signs the task off. Creates fresh users/project/team each run.
"""

import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000/api/v1")
SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "trajectories.jsonl"
PASSWORD = "smoke-password-1"
RUN = str(int(time.time()))
passed = 0


def ok(label: str, response: httpx.Response, status: int, code: str | None = None) -> Any:
    global passed
    body: Any = response.json() if response.content else {}
    body_code = body.get("code", "") if isinstance(body, dict) else ""
    good = response.status_code == status and (code is None or body_code == code)
    print(f"[{'OK ' if good else 'FAIL'}] {label}: {response.status_code} {body_code}".rstrip())
    if not good:
        print(f"       expected {status} {code or ''}; body={body}")
        sys.exit(1)
    passed += 1
    return body


class Client:
    def __init__(self, api: httpx.Client, email: str, password: str) -> None:
        self.api = api
        body = ok(
            f"login {email}",
            api.post("/auth/login", json={"email": email, "password": password}),
            200,
        )
        self.headers = {"Authorization": f"Bearer {body['access_token']}"}
        self.id = body["user"]["id"]

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.api.get(path, headers=self.headers, **kw)

    def post(self, path: str, json: Any = None) -> httpx.Response:
        return self.api.post(path, json=json, headers=self.headers)

    def put(self, path: str, json: Any) -> httpx.Response:
        return self.api.put(path, json=json, headers=self.headers)


def make_user(hr: Client, api: httpx.Client, label: str, roles: list[str]) -> Client:
    email = f"smoke-{label}-{RUN}@example.invalid"
    created = ok(
        f"create {label}",
        hr.post(
            "/users",
            {"email": email, "full_name": f"Smoke {label}", "employment_type": "contractor"},
        ),
        201,
    )
    token = parse_qs(urlparse(created["activation_url"]).query)["token"][0]
    ok(
        f"activate {label}",
        api.post("/auth/activate", json={"token": token, "password": PASSWORD}),
        204,
    )
    for role in roles:
        ok(
            f"grant {role} to {label}",
            hr.post(f"/users/{created['user']['id']}/platform-roles", {"role": role}),
            201,
        )
    return Client(api, email, PASSWORD)


def label_all(view: dict[str, Any], verdict: str = "correct") -> list[dict[str, Any]]:
    return [
        {"item_id": item["id"], "target": target, "value": {"verdict": verdict}}
        for item in view["items"]
        for target in item["payload"]["targets"]
    ]


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=60) as api:
        hr = Client(api, os.environ["SMOKE_HR_EMAIL"], os.environ["SMOKE_HR_PASSWORD"])
        po = make_user(hr, api, "po", ["po"])
        ann = make_user(hr, api, "annotator", ["annotator"])
        rev = make_user(hr, api, "reviewer", ["reviewer"])

        # ---- team ----
        team = ok(
            "create team",
            hr.post("/teams", {"code": f"smoke-{RUN}", "name": f"Smoke team {RUN}"}),
            201,
        )
        ok(
            "add annotator to team",
            hr.post(f"/teams/{team['id']}/members", {"user_id": ann.id, "team_role": "annotator"}),
            201,
        )
        ok(
            "reviewer cannot join as annotator without the role",
            hr.post(f"/teams/{team['id']}/members", {"user_id": rev.id, "team_role": "annotator"}),
            409,
            "role_requirement_not_met",
        )
        ok(
            "add reviewer to team",
            hr.post(f"/teams/{team['id']}/members", {"user_id": rev.id, "team_role": "reviewer"}),
            201,
        )

        # ---- project setup ----
        ok(
            "annotator cannot create project",
            ann.post("/projects", {"code": "x-" + RUN, "name": "x"}),
            403,
            "forbidden",
        )
        project = ok(
            "create project",
            po.post("/projects", {"code": f"smoke-{RUN}", "name": "Smoke project"}),
            201,
        )
        pid = project["id"]
        assert "owner" in project["my_roles"], project
        ok("outsider sees 404", ann.get(f"/projects/{pid}"), 404)
        ok(
            "guideline v1",
            po.post(
                f"/projects/{pid}/guidelines", {"content": "# Guideline\nĐánh giá từng tool call."}
            ),
            201,
        )
        ok("link team", po.post(f"/projects/{pid}/teams", {"team_id": team["id"]}), 201)
        ok("annotator now sees the project", ann.get(f"/projects/{pid}"), 200)

        data = SAMPLE.read_bytes()
        upload = ok(
            "upload url",
            po.post(
                f"/projects/{pid}/datasets/upload-url", {"filename": SAMPLE.name, "size": len(data)}
            ),
            200,
        )
        put = httpx.put(
            upload["url"],
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=60,
        )
        assert put.status_code in (200, 204), put.text
        print("[OK ] put file to storage")
        preview = ok(
            "preview",
            po.post(
                f"/projects/{pid}/datasets/preview",
                {"upload_key": upload["upload_key"], "parser": "jsonl_chat"},
            ),
            200,
        )
        assert preview["report"]["error_count"] == 0, preview["report"]
        dataset = ok(
            "create dataset",
            po.post(
                f"/projects/{pid}/datasets",
                {"upload_key": upload["upload_key"], "parser": "jsonl_chat"},
            ),
            201,
        )
        assert dataset["item_count"] == 3, dataset

        item_types = ok("item types", po.get("/item-types"), 200)
        schema = item_types[0]["default_label_schema"]
        ok(
            "invalid config rejected",
            po.post(f"/projects/{pid}/job-configs", {"label_schema": {"fields": []}}),
            400,
            "label_schema_invalid",
        )
        ok(
            "job config v1",
            po.post(
                f"/projects/{pid}/job-configs",
                {
                    "label_schema": schema,
                    "job_rules": {"items_per_job": 1, "max_rework": 2},
                    "self_check": ["Đã đọc guideline"],
                },
            ),
            201,
        )
        created = ok(
            "create task",
            po.post(
                f"/projects/{pid}/tasks",
                {
                    "name": "Đợt 1",
                    "dataset_version": 1,
                    "job_config_version": 1,
                    "guideline_version": 1,
                    "team_id": team["id"],
                },
            ),
            201,
        )
        assert created["jobs"] == 3, created
        tid = created["task"]["id"]
        ok(
            "task needs active project",
            po.post(f"/projects/{pid}/tasks/{tid}/activate"),
            409,
            "project_not_active",
        )
        ok("activate project", po.post(f"/projects/{pid}/activate"), 200)
        ok("activate task", po.post(f"/projects/{pid}/tasks/{tid}/activate"), 200)

        # ---- labelling and review ----
        ok("reviewer cannot pull annotation work", rev.post(f"/projects/{pid}/jobs/next"), 403)
        first = ok("annotator next job", ann.post(f"/projects/{pid}/jobs/next"), 200)
        jid = first["job"]["id"]
        ok("save draft", ann.put(f"/jobs/{jid}/draft", {"draft": {"note": "wip"}}), 200)
        ok(
            "submit incomplete",
            ann.post(
                f"/jobs/{jid}/submit", {"annotations": label_all(first)[:1], "self_check": [True]}
            ),
            400,
        )
        ok(
            "submit needs self-check",
            ann.post(
                f"/jobs/{jid}/submit", {"annotations": label_all(first), "self_check": [False]}
            ),
            400,
            "self_check_incomplete",
        )
        ok(
            "submit",
            ann.post(
                f"/jobs/{jid}/submit", {"annotations": label_all(first), "self_check": [True]}
            ),
            200,
        )

        to_review = ok("reviewer next", rev.post(f"/projects/{pid}/reviews/next"), 200)
        assert to_review["job"]["id"] == jid
        target = to_review["items"][0]["payload"]["targets"][0]
        ok(
            "reject needs reason",
            rev.post(f"/jobs/{jid}/reviews", {"decision": "reject"}),
            400,
            "reason_required",
        )
        ok(
            "reject",
            rev.post(
                f"/jobs/{jid}/reviews",
                {
                    "decision": "reject",
                    "reason": "Bước đầu sai",
                    "errors": [
                        {
                            "item_id": to_review["items"][0]["id"],
                            "target": target,
                            "reason_code": "WRONG_VERDICT",
                            "severity": "major",
                        }
                    ],
                },
            ),
            201,
        )

        rework = ok("annotator gets the rework first", ann.post(f"/projects/{pid}/jobs/next"), 200)
        assert rework["job"]["id"] == jid and rework["last_review"]["errors"], rework
        ok(
            "resubmit",
            ann.post(
                f"/jobs/{jid}/submit", {"annotations": label_all(rework), "self_check": [True]}
            ),
            200,
        )
        again = ok("reviewer gets the rework", rev.post(f"/projects/{pid}/reviews/next"), 200)
        assert again["job"]["id"] == jid and len(again["rounds"]) == 2
        ok("accept", rev.post(f"/jobs/{jid}/reviews", {"decision": "accept"}), 201)

        for _ in range(5):
            view = ann.post(f"/projects/{pid}/jobs/next")
            if view.status_code == 204:
                print("[OK ] no more jobs: 204")
                break
            view = ok("annotator next job", view, 200)
            ok(
                "submit",
                ann.post(
                    f"/jobs/{view['job']['id']}/submit",
                    {"annotations": label_all(view), "self_check": [True]},
                ),
                200,
            )
            review = ok("reviewer next", rev.post(f"/projects/{pid}/reviews/next"), 200)
            ok(
                "accept",
                rev.post(f"/jobs/{review['job']['id']}/reviews", {"decision": "accept"}),
                201,
            )

        queues = ok("annotator queues", ann.get("/me/queues"), 200)
        assert any(q["project"]["id"] == pid for q in queues)
        progress = ok("progress", po.get(f"/projects/{pid}/progress"), 200)
        assert progress["completion_rate"] == 1.0, progress
        acceptance = ok("acceptance", po.get(f"/projects/{pid}/tasks/{tid}/acceptance"), 200)
        assert acceptance["can_sign_off"], acceptance
        ok("sign off", po.post(f"/projects/{pid}/tasks/{tid}/sign-off"), 200)
        ok("audit for project", hr.get("/audit-events", params={"project_id": pid}), 200)

    print(f"\nAll {passed} checks passed (run {RUN}).")


if __name__ == "__main__":
    main()
