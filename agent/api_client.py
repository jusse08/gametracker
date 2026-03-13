from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from time_utils import utc_now_isoformat


def build_ws_url(server_url: str, agent_token: str) -> str:
    ws_scheme = "wss" if server_url.startswith("https://") else "ws"
    host = server_url.split("://", 1)[-1]
    return f"{ws_scheme}://{host}/api/agent/ws?token={quote(agent_token)}"


def build_ws_log_url(server_url: str) -> str:
    ws_scheme = "wss" if server_url.startswith("https://") else "ws"
    host = server_url.split("://", 1)[-1]
    return f"{ws_scheme}://{host}/api/agent/ws?token=***"


def _error_message(exc: requests.RequestException) -> str:
    response = exc.response
    if response is None:
        return str(exc)

    detail = ""
    try:
        payload = response.json()
    except ValueError:
        detail = response.text.strip()
    else:
        detail = str(payload.get("detail") or payload.get("message") or "").strip()

    if detail:
        return f"{response.status_code} {detail}"
    return f"{response.status_code} {response.reason}"


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
    except requests.RequestException as exc:
        log("API", f"GET /api/agent/config failed: {_error_message(exc)}")
    except ValueError as exc:
        log("API", f"GET /api/agent/config returned invalid JSON: {exc}")
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
    except requests.RequestException as exc:
        log("API", f"GET /api/agent/commands failed: {_error_message(exc)}")
    except ValueError as exc:
        log("API", f"GET /api/agent/commands returned invalid JSON: {exc}")
    return []


def ack_command(
    server_url: str,
    payload: Dict,
    headers: Dict[str, str],
    log: Callable[[str, str], None],
) -> None:
    try:
        response = requests.post(
            f"{server_url}/api/agent/commands/ack",
            json=payload,
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        status_text = "ok" if payload.get("success") else "error"
        log(
            "API",
            "POST /api/agent/commands/ack "
            f"game={payload.get('game_id')} req={payload.get('request_id')} status={status_text}",
        )
    except requests.RequestException as exc:
        log(
            "API",
            "POST /api/agent/commands/ack failed "
            f"game={payload.get('game_id')} req={payload.get('request_id')}: {_error_message(exc)}",
        )


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
    except requests.RequestException as exc:
        error = _error_message(exc)
        log("AUTH", f"Pair failed for device_id={device_id}: {error}")
        return None, error
    except ValueError as exc:
        error = f"Pair returned invalid JSON: {exc}"
        log("AUTH", error)
        return None, error

    token = (payload.get("access_token") or "").strip()
    refresh_token = (payload.get("refresh_token") or "").strip()
    if not token or not refresh_token:
        return None, "Pair response does not contain tokens"
    log("AUTH", f"Pair success for device_id={device_id}")
    return payload, None


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
    except requests.RequestException as exc:
        error = _error_message(exc)
        log("AUTH", f"Token refresh failed for device_id={device_id}: {error}")
        return None, error
    except ValueError as exc:
        error = f"Token refresh returned invalid JSON: {exc}"
        log("AUTH", error)
        return None, error

    token = (payload.get("access_token") or "").strip()
    new_refresh = (payload.get("refresh_token") or "").strip()
    if not token or not new_refresh:
        return None, "Refresh response does not contain tokens"
    log("AUTH", f"Token refresh success for device_id={device_id}")
    return payload, None


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
    except requests.RequestException as exc:
        error = _error_message(exc)
        log("AUTH", f"Device name update failed: {error}")
        return error


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
        "timestamp": utc_now_isoformat(),
    }
    try:
        response = requests.post(
            f"{server_url}/api/sessions/ping",
            json=payload,
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        log("PING", f"Ping ok game_id={game_id} exe={exe_name}")
        return True
    except requests.RequestException as exc:
        log("PING", f"Ping failed game_id={game_id} exe={exe_name}: {_error_message(exc)}")
        return False
