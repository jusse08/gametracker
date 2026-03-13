from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests


def build_ws_url(server_url: str, agent_token: str) -> str:
    ws_scheme = "wss" if server_url.startswith("https://") else "ws"
    host = server_url.split("://", 1)[-1]
    return f"{ws_scheme}://{host}/api/agent/ws?token={quote(agent_token)}"


def build_ws_log_url(server_url: str) -> str:
    ws_scheme = "wss" if server_url.startswith("https://") else "ws"
    host = server_url.split("://", 1)[-1]
    return f"{ws_scheme}://{host}/api/agent/ws?token=***"


def get_agent_config(
    server_url: str,
    headers: Dict[str, str],
    log: Callable[[str, str], None],
) -> Optional[List[Dict]]:
    try:
        response = requests.get(
            f"{server_url}/api/agent/config",
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        log("API", f"GET /api/agent/config -> {len(items)} items")
        return items
    except Exception as e:
        log("API", f"GET /api/agent/config failed: {e}")
        return None


def get_pending_commands(
    server_url: str,
    headers: Dict[str, str],
    log: Callable[[str, str], None],
) -> List[Dict]:
    try:
        response = requests.get(
            f"{server_url}/api/agent/commands",
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        if items:
            log("API", f"GET /api/agent/commands -> {len(items)} commands")
        return items
    except Exception as e:
        log("API", f"GET /api/agent/commands failed: {e}")
        return []


def ack_command(
    server_url: str,
    payload: Dict,
    headers: Dict[str, str],
    log: Callable[[str, str], None],
) -> None:
    try:
        requests.post(
            f"{server_url}/api/agent/commands/ack",
            json=payload,
            headers=headers,
            timeout=5,
        ).raise_for_status()
        status_text = "ok" if payload.get("success") else "error"
        log("API", f"POST /api/agent/commands/ack game={payload.get('game_id')} req={payload.get('request_id')} status={status_text}")
    except Exception as e:
        log("API", f"POST /api/agent/commands/ack failed game={payload.get('game_id')} req={payload.get('request_id')}: {e}")


def pair_agent_device(
    server_url: str,
    pair_code: str,
    device_id: str,
    device_name: str,
    log: Callable[[str, str], None],
) -> Tuple[Optional[Dict], Optional[str]]:
    try:
        response = requests.post(
            f"{server_url}/api/agent/pair",
            json={
                "pair_code": pair_code,
                "device_id": device_id,
                "device_name": device_name,
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        token = (payload.get("access_token") or "").strip()
        refresh_token = (payload.get("refresh_token") or "").strip()
        if not token or not refresh_token:
            return None, "Pair response does not contain tokens"
        log("AUTH", f"Pair success for device_id={device_id}")
        return payload, None
    except Exception as e:
        log("AUTH", f"Pair failed for device_id={device_id}: {e}")
        return None, str(e)


def refresh_agent_token(
    server_url: str,
    device_id: str,
    refresh_token: str,
    log: Callable[[str, str], None],
) -> Tuple[Optional[Dict], Optional[str]]:
    try:
        response = requests.post(
            f"{server_url}/api/agent/auth/refresh",
            json={
                "device_id": device_id,
                "refresh_token": refresh_token,
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        token = (payload.get("access_token") or "").strip()
        new_refresh = (payload.get("refresh_token") or "").strip()
        if not token or not new_refresh:
            return None, "Refresh response does not contain tokens"
        log("AUTH", f"Token refresh success for device_id={device_id}")
        return payload, None
    except Exception as e:
        log("AUTH", f"Token refresh failed for device_id={device_id}: {e}")
        return None, str(e)


def update_agent_device_name(
    server_url: str,
    device_name: str,
    headers: Dict[str, str],
    log: Callable[[str, str], None],
) -> Optional[str]:
    try:
        response = requests.put(
            f"{server_url}/api/agent/device/self",
            json={"device_name": device_name},
            headers=headers,
            timeout=8,
        )
        response.raise_for_status()
        log("AUTH", f"Device name updated on server: {device_name}")
        return None
    except Exception as e:
        log("AUTH", f"Device name update failed: {e}")
        return str(e)


def ping_server(
    server_url: str,
    game_id: int,
    exe_name: str,
    headers: Dict[str, str],
    log: Callable[[str, str], None],
) -> bool:
    payload = {
        "game_id": game_id,
        "exe_name": exe_name,
        "timestamp": datetime.utcnow().isoformat(),
    }
    try:
        requests.post(
            f"{server_url}/api/sessions/ping",
            json=payload,
            headers=headers,
            timeout=5,
        ).raise_for_status()
        log("PING", f"Ping ok game_id={game_id} exe={exe_name}")
        return True
    except Exception as e:
        log("PING", f"Ping failed game_id={game_id} exe={exe_name}: {e}")
        return False
