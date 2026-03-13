import pytest

pytestmark = pytest.mark.anyio


async def test_superadmin_can_delete_regular_user(client, auth_headers):
    create_response = await client.post(
        "/api/users",
        headers=auth_headers,
        json={"username": "temp_user", "password": "password123"},
    )
    assert create_response.status_code == 200, create_response.text
    user_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/users/{user_id}", headers=auth_headers)
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json() == {"ok": True}

    users_response = await client.get("/api/users", headers=auth_headers)
    assert users_response.status_code == 200, users_response.text
    user_ids = [user["id"] for user in users_response.json()]
    assert user_id not in user_ids


async def test_cannot_delete_superadmin(client, auth_headers):
    users_response = await client.get("/api/users", headers=auth_headers)
    assert users_response.status_code == 200, users_response.text

    superadmin = next((u for u in users_response.json() if u["is_superadmin"]), None)
    assert superadmin is not None

    delete_response = await client.delete(f"/api/users/{superadmin['id']}", headers=auth_headers)
    assert delete_response.status_code == 400
    assert delete_response.json()["detail"] == "Cannot delete superadmin"
