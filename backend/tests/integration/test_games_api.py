from app.api.routers import games as games_router


def test_healthcheck(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_create_game_and_import_wiki_items(client, auth_headers, monkeypatch):
    create_response = client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": "Test Game", "status": "playing", "sync_type": "non_steam"},
    )
    assert create_response.status_code == 200, create_response.text
    game_id = create_response.json()["id"]

    monkeypatch.setattr(
        games_router,
        "parse_wiki_missions",
        lambda _: [
            {"title": "Find the relic", "category": "Main Quest"},
            {"title": "Win 3 arena fights", "category": "Side Quest"},
        ],
    )

    import_response = client.post(
        f"/api/games/{game_id}/import/wiki",
        headers=auth_headers,
        json={"url": "https://example.com/wiki"},
    )
    assert import_response.status_code == 200, import_response.text
    imported_items = import_response.json()
    assert len(imported_items) == 2
    assert imported_items[0]["title"] == "Find the relic"
    assert imported_items[0]["category"] == "Main Quest"
    assert imported_items[1]["title"] == "Win 3 arena fights"
    assert imported_items[1]["category"] == "Side Quest"
