from uuid import uuid4

import pytest

from app.api.routers import agent as agent_router

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def reset_pair_rate_limit_state():
    with agent_router.PAIR_ATTEMPTS_LOCK:
        agent_router.PAIR_ATTEMPTS.clear()
    yield
    with agent_router.PAIR_ATTEMPTS_LOCK:
        agent_router.PAIR_ATTEMPTS.clear()


async def _create_non_steam_game(client, auth_headers: dict) -> int:
    response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": f"Agent Security Game {uuid4()}", "status": "playing", "sync_type": "non_steam"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def test_configure_agent_rejects_dangerous_launch_paths(client, auth_headers: dict):
    game_id = await _create_non_steam_game(client, auth_headers)

    bad_paths = [
        "",
        "C:\\Windows\\System32\\cmd.bat",
        "\\\\evil-host\\share\\game.exe",
        "https://example.com/game.exe",
        "relative\\game.exe",
        "C:\\Games\\game.ps1",
    ]

    for launch_path in bad_paths:
        res = await client.post(
            "/api/agent/configure",
            headers=auth_headers,
            json={"game_id": game_id, "launch_path": launch_path, "enabled": True},
        )
        assert res.status_code == 400, (launch_path, res.text)


async def test_configure_agent_accepts_absolute_windows_exe_path(client, auth_headers: dict):
    game_id = await _create_non_steam_game(client, auth_headers)

    res = await client.post(
        "/api/agent/configure",
        headers=auth_headers,
        json={"game_id": game_id, "launch_path": r"C:\\Games\\CoolGame\\game.exe", "enabled": True},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["exe_name"].lower() == "game.exe"


async def test_configure_agent_accepts_windows_path_with_forward_slashes(client, auth_headers: dict):
    game_id = await _create_non_steam_game(client, auth_headers)

    res = await client.post(
        "/api/agent/configure",
        headers=auth_headers,
        json={"game_id": game_id, "launch_path": "C:/Games/CoolGame/game.exe", "enabled": True},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["launch_path"] == r"C:\Games\CoolGame\game.exe"


async def test_configure_agent_rejects_duplicate_launch_path(client, auth_headers: dict):
    first_game_id = await _create_non_steam_game(client, auth_headers)
    second_game_id = await _create_non_steam_game(client, auth_headers)

    first = await client.post(
        "/api/agent/configure",
        headers=auth_headers,
        json={"game_id": first_game_id, "launch_path": r"C:\Games\Shared\game.exe", "enabled": True},
    )
    assert first.status_code == 200, first.text

    duplicate = await client.post(
        "/api/agent/configure",
        headers=auth_headers,
        json={"game_id": second_game_id, "launch_path": r"C:\Games\Shared\game.exe", "enabled": True},
    )
    assert duplicate.status_code == 409, duplicate.text


async def test_agent_pair_refresh_and_revoke_flow(client, auth_headers: dict):
    pair_code_response = await client.post("/api/agent/pair-code", headers=auth_headers)
    assert pair_code_response.status_code == 200, pair_code_response.text
    pair_code = pair_code_response.json()["pair_code"]

    device_id = "gt-test-device-000001"
    pair_response = await client.post(
        "/api/agent/pair",
        json={
            "pair_code": pair_code,
            "device_id": device_id,
            "device_name": "Test Agent Device",
        },
    )
    assert pair_response.status_code == 200, pair_response.text
    payload = pair_response.json()
    access_token = payload["access_token"]
    refresh_token = payload["refresh_token"]

    config_response = await client.get(
        "/api/agent/config",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert config_response.status_code == 200, config_response.text

    refresh_response = await client.post(
        "/api/agent/auth/refresh",
        json={"device_id": device_id, "refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 200, refresh_response.text
    refreshed = refresh_response.json()
    assert refreshed["device_id"] == device_id
    assert refreshed["refresh_token"] != refresh_token

    list_devices = await client.get("/api/agent/devices", headers=auth_headers)
    assert list_devices.status_code == 200, list_devices.text
    assert any(item["device_id"] == device_id for item in list_devices.json())

    revoke_response = await client.post(f"/api/agent/devices/{device_id}/revoke", headers=auth_headers)
    assert revoke_response.status_code == 200, revoke_response.text

    refresh_after_revoke = await client.post(
        "/api/agent/auth/refresh",
        json={"device_id": device_id, "refresh_token": refreshed["refresh_token"]},
    )
    assert refresh_after_revoke.status_code == 401, refresh_after_revoke.text


async def test_agent_device_self_name_update_flow(client, auth_headers: dict):
    pair_code_response = await client.post("/api/agent/pair-code", headers=auth_headers)
    assert pair_code_response.status_code == 200, pair_code_response.text
    pair_code = pair_code_response.json()["pair_code"]

    device_id = f"gt-test-device-{uuid4().hex[:12]}"
    pair_response = await client.post(
        "/api/agent/pair",
        json={
            "pair_code": pair_code,
            "device_id": device_id,
            "device_name": "Initial Name",
        },
    )
    assert pair_response.status_code == 200, pair_response.text
    access_token = pair_response.json()["access_token"]

    update_response = await client.put(
        "/api/agent/device/self",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"device_name": "Renamed Device"},
    )
    assert update_response.status_code == 200, update_response.text
    updated_payload = update_response.json()
    assert updated_payload["ok"] is True
    assert updated_payload["device_id"] == device_id
    assert updated_payload["device_name"] == "Renamed Device"

    list_devices = await client.get("/api/agent/devices", headers=auth_headers)
    assert list_devices.status_code == 200, list_devices.text
    rows = [item for item in list_devices.json() if item["device_id"] == device_id]
    assert rows, "paired device is missing in /api/agent/devices"
    assert rows[0]["device_name"] == "Renamed Device"


async def test_agent_device_self_name_update_requires_agent_token(client, auth_headers: dict):
    pair_code_response = await client.post("/api/agent/pair-code", headers=auth_headers)
    assert pair_code_response.status_code == 200, pair_code_response.text
    pair_code = pair_code_response.json()["pair_code"]

    device_id = f"gt-test-device-{uuid4().hex[:12]}"
    pair_response = await client.post(
        "/api/agent/pair",
        json={
            "pair_code": pair_code,
            "device_id": device_id,
            "device_name": "Initial Name",
        },
    )
    assert pair_response.status_code == 200, pair_response.text

    no_auth = await client.put("/api/agent/device/self", json={"device_name": "X"})
    assert no_auth.status_code == 401, no_auth.text

    user_jwt_auth = await client.put(
        "/api/agent/device/self",
        headers=auth_headers,
        json={"device_name": "X"},
    )
    assert user_jwt_auth.status_code == 401, user_jwt_auth.text


async def test_agent_pair_rate_limit_blocks_bruteforce(client):
    for _ in range(agent_router.AGENT_PAIR_MAX_ATTEMPTS - 1):
        response = await client.post(
            "/api/agent/pair",
            json={
                "pair_code": "000000",
                "device_id": f"gt-test-device-{uuid4().hex[:12]}",
                "device_name": "Rate Limit Probe",
            },
        )
        assert response.status_code == 401, response.text

    blocked = await client.post(
        "/api/agent/pair",
        json={
            "pair_code": "000000",
            "device_id": f"gt-test-device-{uuid4().hex[:12]}",
            "device_name": "Rate Limit Probe",
        },
    )
    assert blocked.status_code == 429, blocked.text
