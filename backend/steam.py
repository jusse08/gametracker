import requests
import re
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select
from database import engine
from models import Settings

def get_steam_settings():
    with Session(engine) as session:
        return session.get(Settings, 1)

def resolve_steam_id(profile_url: str, api_key: Optional[str] = None) -> Optional[str]:
    """
    Extracts SteamID64 from profile URL.
    Supports:
    - https://steamcommunity.com/id/vanityname/
    - https://steamcommunity.com/profiles/76561198000000000/
    """
    if not profile_url:
        return None
        
    # Check if it's already a SteamID in the URL
    profile_match = re.search(r'profiles/(\d+)', profile_url)
    if profile_match:
        return profile_match.group(1)
        
    # Check if it's a vanity URL
    vanity_match = re.search(r'id/([^/]+)', profile_url)
    if vanity_match:
        vanity_name = vanity_match.group(1)
        
        effective_api_key = api_key
        if not effective_api_key:
            settings = get_steam_settings()
            if settings:
                effective_api_key = settings.steam_api_key
        
        if not effective_api_key:
            return None
            
        url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
        params = {
            "key": effective_api_key,
            "vanityurl": vanity_name
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("response", {}).get("success") == 1:
                return data["response"]["steamid"]
        except Exception as e:
            print(f"Error resolving vanity URL: {e}")
            
    return None

def sync_steam_achievements(app_id: int) -> List[Dict[str, Any]]:
    settings = get_steam_settings()
    if not settings or not settings.steam_api_key or not settings.steam_user_id:
        return []

    url = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
    params = {
        "key": settings.steam_api_key,
        "steamid": settings.steam_user_id,
        "appid": app_id,
        "l": "english"
    }
    
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 403:
             # Likely private profile
             return [] # We could raise an error or return a specific flag
             
        data = res.json()
        playerstats = data.get("playerstats", {})
        
        if not playerstats.get("success", False):
            # Potential private profile or game doesn't have achievements
            return []
            
        achievements_data = []
        for ach in playerstats.get("achievements", []):
            achievements_data.append({
                "name": ach.get("name", ach["apiname"]),
                "description": ach.get("description", ""),
                "completed": ach["achieved"] == 1,
                "steam_api_name": ach["apiname"],
                "icon_url": None # We'd need GetSchemaForGame for icons, but let's keep it simple or use a placeholder
            })
            
        # Optional: Get icons from GetSchemaForGame if needed
        # Fallback to a placeholder icon if icon_url is None
        schema_url = "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
        schema_params = {"key": settings.steam_api_key, "appid": app_id}
        schema_res = requests.get(schema_url, params=schema_params, timeout=10)
        schema_data = schema_res.json()
        game_schema = schema_data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
        icon_map = {a["name"]: a["icon"] for a in game_schema}
        
        for ach in achievements_data:
            ach["icon_url"] = icon_map.get(ach["steam_api_name"])
            # Get name and description from schema if missing
            schema_ach = next((a for a in game_schema if a["name"] == ach["steam_api_name"]), None)
            if schema_ach:
                ach["name"] = schema_ach.get("displayName", ach["name"])
                ach["description"] = schema_ach.get("description", ach["description"])

        return achievements_data
    except Exception as e:
        print(f"Steam achievements sync error: {e}")
        return []

def fetch_steam_playtime(app_id: int) -> int:
    settings = get_steam_settings()
    if not settings or not settings.steam_api_key or not settings.steam_user_id:
        return 0

    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": settings.steam_api_key,
        "steamid": settings.steam_user_id,
        "appids_filter[0]": app_id,
        "include_appinfo": 1
    }
    
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        games = data.get("response", {}).get("games", [])
        if games:
            return games[0].get("playtime_forever", 0)
    except Exception as e:
        print(f"Steam playtime fetch error: {e}")
        
    return 0


def fetch_steam_genres(app_id: int) -> List[str]:
    details_url = "https://store.steampowered.com/api/appdetails"
    params = {
        "appids": app_id,
        "l": "english",
        "cc": "US",
    }
    try:
        res = requests.get(details_url, params=params, timeout=10)
        res.raise_for_status()
        payload = res.json()
        app_payload = payload.get(str(app_id), {})
        if not app_payload.get("success"):
            return []
        data = app_payload.get("data", {})
        genres = data.get("genres", [])
        names = [g.get("description", "").strip() for g in genres if isinstance(g, dict)]
        # Keep order and deduplicate.
        unique_names = list(dict.fromkeys([name for name in names if name]))
        return unique_names
    except Exception as e:
        print(f"Steam genres fetch error: {e}")
        return []

def search_steam_games(query: str) -> List[Dict[str, Any]]:
    # This stays as is, it's a public storefront API
    search_url = f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US"
    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        if data.get("items"):
            for item in data["items"]:
                results.append({
                    "title": item["name"],
                    "steam_app_id": item["id"],
                    "cover_url": f"https://cdn.akamai.steamstatic.com/steam/apps/{item['id']}/header.jpg",
                    "sync_type": "steam"
                })
        return results
    except Exception as e:
        print(f"Steam search error: {e}")
        return []
