import logging
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def build_steam_store_image_urls(app_id: int) -> Dict[str, str]:
    base = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}"
    return {
        "poster": f"{base}/library_600x900.jpg",
        "poster2x": f"{base}/library_600x900_2x.jpg",
        "hero": f"{base}/library_hero.jpg",
        "hero_blur": f"{base}/library_hero_blur.jpg",
        "header": f"{base}/header.jpg",
        "capsule_main": f"{base}/capsule_616x353.jpg",
    }


def resolve_steam_id(profile_url: str, api_key: Optional[str] = None) -> Optional[str]:
    """
    Extract SteamID64 from profile URL.
    Supports:
    - https://steamcommunity.com/id/vanityname/
    - https://steamcommunity.com/profiles/76561198000000000/
    """
    if not profile_url:
        return None

    profile_match = re.search(r"profiles/(\d+)", profile_url)
    if profile_match:
        return profile_match.group(1)

    vanity_match = re.search(r"id/([^/]+)", profile_url)
    if not vanity_match or not api_key:
        return None

    url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
    params = {"key": api_key, "vanityurl": vanity_match.group(1)}
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Failed to resolve Steam vanity URL")
        return None

    if data.get("response", {}).get("success") == 1:
        return data["response"].get("steamid")
    return None


def sync_steam_achievements(
    app_id: int,
    steam_api_key: Optional[str],
    steam_user_id: Optional[str],
) -> List[Dict[str, Any]]:
    if not steam_api_key or not steam_user_id:
        return []

    url = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
    params = {
        "key": steam_api_key,
        "steamid": steam_user_id,
        "appid": app_id,
        "l": "english",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
            if response.status_code == 403:
                return []
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Steam achievements sync error")
        return []

    playerstats = data.get("playerstats", {})
    if not playerstats.get("success", False):
        return []

    achievements_data: List[Dict[str, Any]] = []
    for achievement in playerstats.get("achievements", []):
        api_name = achievement.get("apiname")
        if not api_name:
            continue
        achievements_data.append(
            {
                "name": achievement.get("name") or api_name,
                "description": achievement.get("description", ""),
                "completed": achievement.get("achieved") == 1,
                "steam_api_name": api_name,
                "icon_url": None,
            }
        )

    schema_url = "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
    schema_params = {"key": steam_api_key, "appid": app_id}
    try:
        with httpx.Client(timeout=10.0) as client:
            schema_response = client.get(schema_url, params=schema_params)
            schema_response.raise_for_status()
            schema_data = schema_response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Steam schema fetch failed for app_id=%s", app_id, exc_info=True)
        return achievements_data

    game_schema = schema_data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
    schema_by_name = {
        item["name"]: item for item in game_schema if isinstance(item, dict) and item.get("name")
    }

    for achievement in achievements_data:
        schema_item = schema_by_name.get(achievement["steam_api_name"])
        if not schema_item:
            continue
        achievement["icon_url"] = schema_item.get("icon")
        achievement["name"] = schema_item.get("displayName", achievement["name"])
        achievement["description"] = schema_item.get("description", achievement["description"])

    return achievements_data


def fetch_steam_playtime(
    app_id: int, steam_api_key: Optional[str], steam_user_id: Optional[str]
) -> int:
    if not steam_api_key or not steam_user_id:
        return 0

    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": steam_api_key,
        "steamid": steam_user_id,
        "appids_filter[0]": app_id,
        "include_appinfo": 1,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Steam playtime fetch error")
        return 0

    games = data.get("response", {}).get("games", [])
    if games:
        return int(games[0].get("playtime_forever", 0) or 0)
    return 0


def fetch_steam_genres(app_id: int) -> List[str]:
    details_url = "https://store.steampowered.com/api/appdetails"
    params = {
        "appids": app_id,
        "l": "english",
        "cc": "US",
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(details_url, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Steam genres fetch error")
        return []

    app_payload = payload.get(str(app_id), {})
    if not app_payload.get("success"):
        return []
    data = app_payload.get("data", {})
    genres = data.get("genres", [])
    names = [genre.get("description", "").strip() for genre in genres if isinstance(genre, dict)]
    return list(dict.fromkeys([name for name in names if name]))


def search_steam_games(query: str) -> List[Dict[str, Any]]:
    search_url = f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(search_url)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Steam search error")
        return []

    results = []
    for item in data.get("items", []):
        app_id = item.get("id")
        name = item.get("name")
        if not app_id or not name:
            continue
        cover_urls = build_steam_store_image_urls(app_id)
        results.append(
            {
                "title": name,
                "steam_app_id": app_id,
                "cover_url": cover_urls["poster2x"],
                "cover_urls": cover_urls,
                "sync_type": "steam",
            }
        )
    return results
