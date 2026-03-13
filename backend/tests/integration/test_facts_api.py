import pytest

from app.api.routers import facts as facts_router

pytestmark = pytest.mark.anyio


async def test_read_random_fact(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        facts_router,
        "fetch_random_fandom_fact",
        lambda: {
            "text": "Did you know? Sonic loves chili dogs.",
            "game_title": "Sonic the Hedgehog",
            "source": "fandom",
        },
    )

    response = await client.get("/api/facts/random", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "fandom"
    assert payload["game_title"] == "Sonic the Hedgehog"
    assert "Did you know?" in payload["text"]


async def test_rebuild_facts_for_superadmin(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        facts_router,
        "collect_fandom_facts",
        lambda **_: [{"title": "Malenia", "fact": "Did you know? Malenia is feared across the Lands Between."}],
    )
    monkeypatch.setattr(
        facts_router,
        "save_facts_json",
        lambda facts: "/tmp/game_facts.json",
    )

    response = await client.post(
        "/api/facts/rebuild",
        headers=auth_headers,
        json={"per_seed_limit": 5, "max_facts": 10},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] == 1


async def test_rebuild_facts_from_single_page(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        facts_router,
        "collect_facts_from_fandom_page",
        lambda **_: [
            {
                "game": "Stardew Valley",
                "title": "Секреты",
                "fact": "Главное меню: на экране есть скрытые пасхалки.",
                "source": "fandom",
            }
        ],
    )
    monkeypatch.setattr(
        facts_router,
        "save_facts_json",
        lambda facts: "/tmp/game_facts.json",
    )

    response = await client.post(
        "/api/facts/rebuild",
        headers=auth_headers,
        json={
            "page_url": "https://stardewvalley.fandom.com/ru/wiki/%D0%A1%D0%B5%D0%BA%D1%80%D0%B5%D1%82%D1%8B",
            "game": "Stardew Valley",
            "max_facts": 30,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] == 1
