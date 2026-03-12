from fastapi.testclient import TestClient
from uuid import uuid4


def _create_non_steam_game(client: TestClient, auth_headers: dict) -> int:
    response = client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": f"Agent Security Game {uuid4()}", "status": "playing", "sync_type": "non_steam"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_configure_agent_rejects_dangerous_launch_paths(client: TestClient, auth_headers: dict):
    game_id = _create_non_steam_game(client, auth_headers)

    bad_paths = [
        "",
        "C:\\Windows\\System32\\cmd.bat",
        "\\\\evil-host\\share\\game.exe",
        "https://example.com/game.exe",
        "relative\\game.exe",
        "C:/Games/game.exe",
        "C:\\Games\\game.ps1",
    ]

    for launch_path in bad_paths:
        res = client.post(
            "/api/agent/configure",
            headers=auth_headers,
            json={"game_id": game_id, "launch_path": launch_path, "enabled": True},
        )
        assert res.status_code == 400, (launch_path, res.text)


def test_configure_agent_accepts_absolute_windows_exe_path(client: TestClient, auth_headers: dict):
    game_id = _create_non_steam_game(client, auth_headers)

    res = client.post(
        "/api/agent/configure",
        headers=auth_headers,
        json={"game_id": game_id, "launch_path": r"C:\\Games\\CoolGame\\game.exe", "enabled": True},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["exe_name"].lower() == "game.exe"
