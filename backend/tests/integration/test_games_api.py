import pytest
from sqlmodel import Session, select

from app.api.routers import games as games_router
from app.core.database import engine
from app.domain.models import Achievement, ChecklistItem, QuestCategory

pytestmark = pytest.mark.anyio


async def test_healthcheck(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"


async def test_readiness_check(client):
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_create_game_and_import_wiki_items(client, auth_headers, monkeypatch):
    create_response = await client.post(
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

    import_response = await client.post(
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


async def test_read_checklist_categories_does_not_mutate_database(client, auth_headers):
    create_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": "Category Read Game", "status": "playing", "sync_type": "non_steam"},
    )
    assert create_response.status_code == 200, create_response.text
    game_id = create_response.json()["id"]

    with Session(engine) as session:
        session.add(ChecklistItem(game_id=game_id, title="Legacy Item", category="Legacy Category", sort_order=0))
        session.commit()

    response = await client.get(f"/api/games/{game_id}/checklist/categories", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == []

    with Session(engine) as session:
        categories = session.exec(select(QuestCategory).where(QuestCategory.game_id == game_id)).all()
        assert categories == []


async def test_delete_checklist_category_is_case_insensitive(client, auth_headers):
    create_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": "Category Delete Game", "status": "playing", "sync_type": "non_steam"},
    )
    assert create_response.status_code == 200, create_response.text
    game_id = create_response.json()["id"]

    category_response = await client.post(
        f"/api/games/{game_id}/checklist/categories",
        headers=auth_headers,
        json={"name": "Main Quest"},
    )
    assert category_response.status_code == 200, category_response.text

    item_response = await client.post(
        f"/api/games/{game_id}/checklist",
        headers=auth_headers,
        json={"title": "Find relic", "category": "Main Quest"},
    )
    assert item_response.status_code == 200, item_response.text

    delete_response = await client.delete(
        f"/api/games/{game_id}/checklist/category/main quest",
        headers=auth_headers,
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["deleted_count"] == 1

    checklist_response = await client.get(f"/api/games/{game_id}/checklist", headers=auth_headers)
    assert checklist_response.status_code == 200, checklist_response.text
    assert checklist_response.json() == []

    categories_response = await client.get(f"/api/games/{game_id}/checklist/categories", headers=auth_headers)
    assert categories_response.status_code == 200, categories_response.text
    assert categories_response.json() == []


async def test_game_progress_summary_is_aggregated_in_single_response(client, auth_headers):
    steam_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={
            "title": "Steam Progress Game",
            "status": "playing",
            "sync_type": "steam",
            "steam_app_id": 10,
        },
    )
    assert steam_response.status_code == 200, steam_response.text
    steam_game_id = steam_response.json()["id"]

    non_steam_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": "Quest Progress Game", "status": "playing", "sync_type": "non_steam"},
    )
    assert non_steam_response.status_code == 200, non_steam_response.text
    non_steam_game_id = non_steam_response.json()["id"]

    with Session(engine) as session:
        session.add(ChecklistItem(game_id=steam_game_id, title="Quest 1", category="Main", completed=True, sort_order=0))
        session.add(ChecklistItem(game_id=steam_game_id, title="Quest 2", category="Main", completed=False, sort_order=1))
        session.add(Achievement(game_id=steam_game_id, name="Ach 1", completed=True))
        session.add(Achievement(game_id=steam_game_id, name="Ach 2", completed=False))
        session.add(ChecklistItem(game_id=non_steam_game_id, title="Task 1", category="Main", completed=True, sort_order=0))
        session.add(ChecklistItem(game_id=non_steam_game_id, title="Task 2", category="Main", completed=False, sort_order=1))
        session.commit()

    response = await client.get("/api/games/progress-summary", headers=auth_headers)
    assert response.status_code == 200, response.text
    items = {item["game_id"]: item for item in response.json()["items"]}

    assert items[steam_game_id]["checklist_total"] == 2
    assert items[steam_game_id]["checklist_completed"] == 1
    assert items[steam_game_id]["achievement_total"] == 2
    assert items[steam_game_id]["achievement_completed"] == 1
    assert items[steam_game_id]["progress_percent"] == 50

    assert items[non_steam_game_id]["checklist_total"] == 2
    assert items[non_steam_game_id]["checklist_completed"] == 1
    assert items[non_steam_game_id]["achievement_total"] == 0
    assert items[non_steam_game_id]["achievement_completed"] == 0
    assert items[non_steam_game_id]["progress_percent"] == 50


async def test_update_checklist_item_uses_json_body(client, auth_headers):
    create_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": "Checklist Body Game", "status": "playing", "sync_type": "non_steam"},
    )
    assert create_response.status_code == 200, create_response.text
    game_id = create_response.json()["id"]

    item_response = await client.post(
        f"/api/games/{game_id}/checklist",
        headers=auth_headers,
        json={"title": "Find relic", "category": "Main Quest"},
    )
    assert item_response.status_code == 200, item_response.text
    item_id = item_response.json()["id"]

    bad_response = await client.put(f"/api/checklist/{item_id}?completed=true", headers=auth_headers)
    assert bad_response.status_code == 422, bad_response.text

    update_response = await client.put(
        f"/api/checklist/{item_id}",
        headers=auth_headers,
        json={"completed": True},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["completed"] is True


async def test_update_note_uses_json_body(client, auth_headers):
    create_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": "Note Body Game", "status": "playing", "sync_type": "non_steam"},
    )
    assert create_response.status_code == 200, create_response.text
    game_id = create_response.json()["id"]

    note_response = await client.post(
        f"/api/games/{game_id}/notes",
        headers=auth_headers,
        json={"text": "Old note"},
    )
    assert note_response.status_code == 200, note_response.text
    note_id = note_response.json()["id"]

    bad_response = await client.put(
        f"/api/notes/{note_id}?text=Updated%20from%20query",
        headers=auth_headers,
    )
    assert bad_response.status_code == 422, bad_response.text

    update_response = await client.put(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"text": "Updated from body"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["text"] == "Updated from body"


async def test_progress_summary_handles_steam_games_without_checklist(client, auth_headers):
    create_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={
            "title": "Steam Achievement Only",
            "status": "playing",
            "sync_type": "steam",
            "steam_app_id": 20,
        },
    )
    assert create_response.status_code == 200, create_response.text
    game_id = create_response.json()["id"]

    with Session(engine) as session:
        session.add(Achievement(game_id=game_id, name="Ach 1", completed=True))
        session.add(Achievement(game_id=game_id, name="Ach 2", completed=False))
        session.commit()

    response = await client.get("/api/games/progress-summary", headers=auth_headers)
    assert response.status_code == 200, response.text
    items = {item["game_id"]: item for item in response.json()["items"]}

    assert items[game_id]["checklist_total"] == 0
    assert items[game_id]["achievement_total"] == 2
    assert items[game_id]["achievement_completed"] == 1
    assert items[game_id]["progress_percent"] == 50


async def test_progress_summary_returns_zero_for_empty_games(client, auth_headers):
    create_response = await client.post(
        "/api/games",
        headers=auth_headers,
        json={"title": "Empty Progress Game", "status": "playing", "sync_type": "non_steam"},
    )
    assert create_response.status_code == 200, create_response.text
    game_id = create_response.json()["id"]

    response = await client.get("/api/games/progress-summary", headers=auth_headers)
    assert response.status_code == 200, response.text
    items = {item["game_id"]: item for item in response.json()["items"]}

    assert items[game_id] == {
        "game_id": game_id,
        "progress_percent": 0,
        "checklist_total": 0,
        "checklist_completed": 0,
        "achievement_total": 0,
        "achievement_completed": 0,
    }
