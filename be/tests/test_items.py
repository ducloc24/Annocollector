import pytest


async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


async def test_item_crud_flow(client):
    created = await client.post(
        "/api/v1/items",
        json={"name": "Notebook", "description": "A5 dotted", "price": 12.5},
    )
    assert created.status_code == 201
    item = created.json()
    assert item["name"] == "Notebook"
    assert item["price"] == 12.5
    item_id = item["id"]

    listed = await client.get("/api/v1/items")
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == item_id

    fetched = await client.get(f"/api/v1/items/{item_id}")
    assert fetched.status_code == 200

    updated = await client.patch(f"/api/v1/items/{item_id}", json={"price": 9.99})
    assert updated.status_code == 200
    assert updated.json()["price"] == 9.99

    deleted = await client.delete(f"/api/v1/items/{item_id}")
    assert deleted.status_code == 204

    missing = await client.get(f"/api/v1/items/{item_id}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"


async def test_create_item_validation_error(client):
    response = await client.post("/api/v1/items", json={"name": "", "price": -1})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("search, expected", [("note", 1), ("xyz", 0)])
async def test_search_filter(client, search, expected):
    await client.post("/api/v1/items", json={"name": "Notebook"})
    response = await client.get("/api/v1/items", params={"search": search})
    assert response.json()["total"] == expected
