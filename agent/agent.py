import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from ctypes import wintypes
from datetime import datetime
from typing import Deque, Dict, List, Optional, Tuple
from urllib.parse import quote

import psutil
import requests

APP_NAME = "GameTracker"
AGENT_SETTINGS_FILENAME = "agent_settings.json"
AGENT_TOKEN_FILENAME = "agent_auth.bin"

PING_INTERVAL_SECONDS = 30
COMMAND_POLL_INTERVAL_SECONDS = 6
CONFIG_FALLBACK_POLL_SECONDS = 5
WS_RECONNECT_DELAY_SECONDS = 3
PAIR_CODE_RE = re.compile(r"^\d{6}$")
WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
MAX_DEBUG_LOG_LINES = 4000


class DebugLogStore:
    def __init__(self, max_lines: int = MAX_DEBUG_LOG_LINES) -> None:
        self._lock = threading.Lock()
        self._entries: Deque[str] = deque()
        self._base_index = 0
        self._max_lines = max(100, int(max_lines))

    def add(self, scope: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} [{scope}] {message}"
        with self._lock:
            self._entries.append(line)
            overflow = len(self._entries) - self._max_lines
            if overflow > 0:
                for _ in range(overflow):
                    self._entries.popleft()
                self._base_index += overflow

    def read_since(self, cursor: int) -> Tuple[int, List[str]]:
        with self._lock:
            effective_cursor = max(int(cursor or 0), self._base_index)
            start = effective_cursor - self._base_index
            data = list(self._entries)[start:]
            next_cursor = self._base_index + len(self._entries)
            return next_cursor, data

    def clear(self) -> int:
        with self._lock:
            self._base_index += len(self._entries)
            self._entries.clear()
            return self._base_index


DEBUG_LOG_STORE: Optional[DebugLogStore] = None


def set_debug_log_store(store: Optional[DebugLogStore]) -> None:
    global DEBUG_LOG_STORE
    DEBUG_LOG_STORE = store


def debug_log(scope: str, message: str) -> None:
    store = DEBUG_LOG_STORE
    if store is None:
        return
    try:
        store.add(scope, message)
    except Exception:
        pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _bytes_to_blob(data: bytes) -> DATA_BLOB:
    if not data:
        return DATA_BLOB(0, None)
    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.cbData or not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def encrypt_for_current_user(raw_data: bytes) -> bytes:
    if os.name != "nt":
        return raw_data
    in_blob = _bytes_to_blob(raw_data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob)):
        raise OSError("CryptProtectData failed")
    try:
        return _blob_to_bytes(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def decrypt_for_current_user(encrypted_data: bytes) -> bytes:
    if os.name != "nt":
        return encrypted_data
    in_blob = _bytes_to_blob(encrypted_data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob)):
        raise OSError("CryptUnprotectData failed")
    try:
        return _blob_to_bytes(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def get_storage_dir() -> str:
    if os.name == "nt":
        base = os.getenv("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".config", "gametracker")


def get_settings_path() -> str:
    return os.path.join(get_storage_dir(), AGENT_SETTINGS_FILENAME)


def get_token_path() -> str:
    return os.path.join(get_storage_dir(), AGENT_TOKEN_FILENAME)


def validate_agent_token(raw_token: str) -> Tuple[str, Optional[str]]:
    token = (raw_token or "").strip()
    if not token:
        return "", "empty token"
    if any(ord(ch) > 127 for ch in token):
        return "", "token contains non-ASCII characters"
    if token.count(".") == 2 and len(token) >= 40:
        return token, None
    return "", "agent access token must be JWT from pairing flow"


def is_jwt_token(token: str) -> bool:
    return (token or "").count(".") == 2


def validate_server_url(raw_url: str) -> Tuple[str, Optional[str]]:
    url = (raw_url or "").strip().rstrip("/")
    if not url:
        return "", "empty server url"
    if not (url.startswith("http://") or url.startswith("https://")):
        return "", "server url must start with http:// or https://"
    return url, None


def normalize_launch_path(launch_path: str) -> Tuple[str, Optional[str]]:
    path = (launch_path or "").strip().strip('"')
    if not path:
        return "", "empty launch_path"
    if "\x00" in path:
        return "", "launch_path contains null byte"
    if path.startswith("\\\\"):
        return "", "UNC path is not allowed"
    if path.startswith("http://") or path.startswith("https://"):
        return "", "URL launch paths are not allowed"
    if not WINDOWS_ABS_PATH_RE.match(path):
        return "", "path must be absolute Windows path"

    normalized = path.replace("/", "\\")
    if not normalized.lower().endswith(".exe"):
        return "", "path must point to .exe"
    return normalized, None


def validate_launch_path(launch_path: str) -> Tuple[bool, Optional[str]]:
    _, err = normalize_launch_path(launch_path)
    return err is None, err


class SharedState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config_items: List[Dict] = []
        self._ws_connected = False
        self._last_error = ""

    def set_config_items(self, items: List[Dict]) -> None:
        with self._lock:
            self._config_items = list(items or [])

    def get_config_items(self) -> List[Dict]:
        with self._lock:
            return list(self._config_items)

    def set_ws_connected(self, value: bool) -> None:
        with self._lock:
            self._ws_connected = bool(value)

    def is_ws_connected(self) -> bool:
        with self._lock:
            return self._ws_connected

    def set_last_error(self, value: str) -> None:
        with self._lock:
            self._last_error = value or ""

    def get_last_error(self) -> str:
        with self._lock:
            return self._last_error


class SettingsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token = ""
        self._refresh_token = ""
        self._device_id = ""
        self._access_expires_at = 0
        self._device_name = ""
        self._autostart = False
        self._server_url = ""

    def load(self) -> None:
        os.makedirs(get_storage_dir(), exist_ok=True)
        token = ""
        refresh_token = ""
        device_id = ""
        access_expires_at = 0
        device_name = ""
        token_path = get_token_path()
        if os.path.exists(token_path):
            try:
                with open(token_path, "rb") as f:
                    decoded = decrypt_for_current_user(f.read()).decode("utf-8").strip()
                    try:
                        payload = json.loads(decoded)
                        if isinstance(payload, dict):
                            token = str(payload.get("token") or "").strip()
                            refresh_token = str(payload.get("refresh_token") or "").strip()
                            device_id = str(payload.get("device_id") or "").strip()
                            access_expires_at = int(payload.get("access_expires_at") or 0)
                            device_name = str(payload.get("device_name") or "").strip()
                        else:
                            token = decoded
                    except Exception:
                        token = decoded
            except Exception:
                token = ""
        autostart = False
        server_url = ""
        settings_path = get_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                    autostart = bool(payload.get("autostart", False))
                    server_url = (payload.get("server_url") or "").strip().rstrip("/")
            except Exception:
                autostart = False
                server_url = ""
        with self._lock:
            self._token = token
            self._refresh_token = refresh_token
            self._device_id = device_id
            self._access_expires_at = access_expires_at
            self._device_name = device_name
            self._autostart = autostart
            self._server_url = server_url

    def save(self) -> None:
        with self._lock:
            token = self._token
            refresh_token = self._refresh_token
            device_id = self._device_id
            access_expires_at = self._access_expires_at
            device_name = self._device_name
            autostart = self._autostart
            server_url = self._server_url
        os.makedirs(get_storage_dir(), exist_ok=True)
        try:
            token_payload = json.dumps(
                {
                    "token": token,
                    "refresh_token": refresh_token,
                    "device_id": device_id,
                    "access_expires_at": access_expires_at,
                    "device_name": device_name,
                },
                ensure_ascii=True,
            )
            with open(get_token_path(), "wb") as f:
                f.write(encrypt_for_current_user(token_payload.encode("utf-8")))
        except Exception:
            pass
        try:
            with open(get_settings_path(), "w", encoding="utf-8") as f:
                json.dump({"autostart": autostart, "server_url": server_url}, f, ensure_ascii=True, indent=2)
        except Exception:
            pass

    def set_token(self, token: str) -> None:
        with self._lock:
            self._token = token.strip()

    def get_token(self) -> str:
        with self._lock:
            return self._token

    def set_refresh_token(self, refresh_token: str) -> None:
        with self._lock:
            self._refresh_token = refresh_token.strip()

    def get_refresh_token(self) -> str:
        with self._lock:
            return self._refresh_token

    def set_device_id(self, device_id: str) -> None:
        with self._lock:
            self._device_id = device_id.strip()

    def get_device_id(self) -> str:
        with self._lock:
            return self._device_id

    def set_access_expires_at(self, ts: int) -> None:
        with self._lock:
            self._access_expires_at = int(ts or 0)

    def get_access_expires_at(self) -> int:
        with self._lock:
            return self._access_expires_at

    def set_device_name(self, name: str) -> None:
        with self._lock:
            self._device_name = name.strip()

    def get_device_name(self) -> str:
        with self._lock:
            return self._device_name

    def set_autostart(self, value: bool) -> None:
        with self._lock:
            self._autostart = bool(value)

    def get_autostart(self) -> bool:
        with self._lock:
            return self._autostart

    def set_server_url(self, server_url: str) -> None:
        with self._lock:
            self._server_url = server_url.strip().rstrip("/")

    def get_server_url(self) -> str:
        with self._lock:
            return self._server_url


def get_agent_headers(agent_token: str) -> Dict[str, str]:
    token, err = validate_agent_token(agent_token)
    if err:
        raise ValueError(f"Invalid agent token: {err}")
    return {"Authorization": f"Bearer {token}"}


def build_ws_url(server_url: str, agent_token: str) -> str:
    ws_scheme = "wss" if server_url.startswith("https://") else "ws"
    host = server_url.split("://", 1)[-1]
    return f"{ws_scheme}://{host}/api/agent/ws?token={quote(agent_token)}"


def build_ws_log_url(server_url: str) -> str:
    ws_scheme = "wss" if server_url.startswith("https://") else "ws"
    host = server_url.split("://", 1)[-1]
    return f"{ws_scheme}://{host}/api/agent/ws?token=***"


def get_agent_config(server_url: str, agent_token: str) -> Optional[List[Dict]]:
    try:
        response = requests.get(
            f"{server_url}/api/agent/config",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        debug_log("API", f"GET /api/agent/config -> {len(items)} items")
        return items
    except Exception as e:
        debug_log("API", f"GET /api/agent/config failed: {e}")
        return None


def get_pending_commands(server_url: str, agent_token: str) -> List[Dict]:
    try:
        response = requests.get(
            f"{server_url}/api/agent/commands",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        if items:
            debug_log("API", f"GET /api/agent/commands -> {len(items)} commands")
        return items
    except Exception as e:
        debug_log("API", f"GET /api/agent/commands failed: {e}")
        return []


def ack_command(
    server_url: str,
    game_id: int,
    request_id: str,
    success: bool,
    agent_token: str,
    error: Optional[str] = None,
) -> None:
    payload = {
        "game_id": game_id,
        "request_id": request_id,
        "success": success,
        "error": error,
    }
    try:
        requests.post(
            f"{server_url}/api/agent/commands/ack",
            json=payload,
            headers=get_agent_headers(agent_token),
            timeout=5,
        ).raise_for_status()
        status_text = "ok" if success else "error"
        debug_log("API", f"POST /api/agent/commands/ack game={game_id} req={request_id} status={status_text}")
    except Exception as e:
        debug_log("API", f"POST /api/agent/commands/ack failed game={game_id} req={request_id}: {e}")
        pass


def pair_agent_device(
    server_url: str,
    pair_code: str,
    device_id: str,
    device_name: str,
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
        debug_log("AUTH", f"Pair success for device_id={device_id}")
        return payload, None
    except Exception as e:
        debug_log("AUTH", f"Pair failed for device_id={device_id}: {e}")
        return None, str(e)


def refresh_agent_token(server_url: str, device_id: str, refresh_token: str) -> Tuple[Optional[Dict], Optional[str]]:
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
        debug_log("AUTH", f"Token refresh success for device_id={device_id}")
        return payload, None
    except Exception as e:
        debug_log("AUTH", f"Token refresh failed for device_id={device_id}: {e}")
        return None, str(e)


def launch_game(launch_path: str) -> Tuple[bool, Optional[str]]:
    normalized_launch_path, err = normalize_launch_path(launch_path)
    if err:
        debug_log("LAUNCH", f"Launch rejected path='{launch_path}': {err}")
        return False, err
    try:
        if os.name == "nt":
            os.startfile(normalized_launch_path)
        else:
            subprocess.Popen([normalized_launch_path])
        debug_log("LAUNCH", f"Launch started: {normalized_launch_path}")
        return True, None
    except Exception as e:
        debug_log("LAUNCH", f"Launch failed: {normalized_launch_path} ({e})")
        return False, str(e)


def ping_server(server_url: str, game_id: int, exe_name: str, agent_token: str) -> bool:
    payload = {
        "game_id": game_id,
        "exe_name": exe_name,
        "timestamp": datetime.utcnow().isoformat(),
    }
    try:
        requests.post(
            f"{server_url}/api/sessions/ping",
            json=payload,
            headers=get_agent_headers(agent_token),
            timeout=5,
        ).raise_for_status()
        debug_log("PING", f"Ping ok game_id={game_id} exe={exe_name}")
        return True
    except Exception as e:
        debug_log("PING", f"Ping failed game_id={game_id} exe={exe_name}: {e}")
        return False


def run_command_processor(server_url: str, agent_token: str) -> None:
    commands = get_pending_commands(server_url, agent_token)
    if commands:
        debug_log("CMD", f"Processing {len(commands)} pending command(s)")
    for command in commands:
        game_id = command.get("game_id")
        request_id = command.get("request_id")
        launch_path = (command.get("launch_path") or "").strip()
        if not game_id or not request_id or not launch_path:
            debug_log("CMD", "Skipped command with missing fields")
            continue
        debug_log("CMD", f"Launch command game_id={game_id} req={request_id}")
        success, error = launch_game(launch_path)
        ack_command(server_url, game_id, request_id, success, agent_token, error)


def build_unique_exe_targets(config_items: List[Dict]) -> Dict[str, int]:
    owners: Dict[str, List[int]] = {}
    for item in config_items:
        if not item.get("enabled", True):
            continue
        exe = (item.get("exe_name") or "").strip().lower()
        game_id = item.get("game_id")
        if not exe or not game_id:
            continue
        owners.setdefault(exe, []).append(int(game_id))

    result: Dict[str, int] = {}
    for exe, game_ids in owners.items():
        if len(game_ids) == 1:
            result[exe] = game_ids[0]
    return result


def check_processes_and_ping(server_url: str, config_items: List[Dict], agent_token: str) -> int:
    targets = build_unique_exe_targets(config_items)
    if not targets:
        debug_log("PING", "No unique exe targets to watch")
        return 0

    running_exes = set()
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").strip().lower()
            if name:
                running_exes.add(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    pinged = 0
    for exe_name, game_id in targets.items():
        if exe_name in running_exes and ping_server(server_url, game_id, exe_name, agent_token):
            pinged += 1
    debug_log("PING", f"Process scan: targets={len(targets)} running={len(running_exes)} pinged={pinged}")
    return pinged


def default_device_name() -> str:
    host = os.getenv("COMPUTERNAME") or os.getenv("HOSTNAME") or "Agent-PC"
    return f"GameTracker Agent ({host})"


def apply_agent_auth_payload(settings_store: SettingsStore, payload: Dict) -> None:
    token = (payload.get("access_token") or "").strip()
    refresh_token = (payload.get("refresh_token") or "").strip()
    device_id = (payload.get("device_id") or "").strip()
    device_name = (payload.get("device_name") or "").strip()
    expires_in = int(payload.get("access_expires_in") or 0)
    expires_at = int(time.time()) + max(expires_in, 1)

    settings_store.set_token(token)
    settings_store.set_refresh_token(refresh_token)
    if device_id:
        settings_store.set_device_id(device_id)
    if device_name:
        settings_store.set_device_name(device_name)
    settings_store.set_access_expires_at(expires_at)
    settings_store.save()


def refresh_if_needed(settings_store: SettingsStore, server_url: str, force: bool = False) -> Tuple[str, Optional[str]]:
    token = settings_store.get_token().strip()
    refresh_token = settings_store.get_refresh_token().strip()
    device_id = settings_store.get_device_id().strip()
    expires_at = settings_store.get_access_expires_at()
    now = int(time.time())

    should_refresh = force
    if token and refresh_token and device_id and is_jwt_token(token):
        if not expires_at or now >= (expires_at - 60):
            should_refresh = True

    if should_refresh and refresh_token and device_id:
        debug_log("AUTH", f"Refreshing access token for device_id={device_id}")
        payload, err = refresh_agent_token(server_url, device_id, refresh_token)
        if err:
            return token, err
        apply_agent_auth_payload(settings_store, payload or {})
        token = settings_store.get_token().strip()
    return token, None


def get_autostart_command() -> Optional[str]:
    if os.name != "nt":
        return None
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}" --background'

    python_exe = os.path.abspath(sys.executable)
    pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
    runner = pythonw_exe if os.path.exists(pythonw_exe) else python_exe
    script_path = os.path.abspath(__file__)
    return f'"{runner}" "{script_path}" --background'


def set_autostart_windows(enabled: bool) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Autostart is supported only on Windows"
    try:
        import winreg

        run_key_path = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path, 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                cmd = get_autostart_command()
                if not cmd:
                    return False, "Unable to build autostart command"
                winreg.SetValueEx(key, "GameTrackerAgent", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "GameTrackerAgent")
                except FileNotFoundError:
                    pass
            return True, ""
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        return False, str(e)


def is_autostart_enabled_windows() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        run_key_path = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, "GameTrackerAgent")
            return bool(value)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def ws_worker(
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    command_refresh_event: threading.Event,
    settings_store: SettingsStore,
    shared_state: SharedState,
) -> None:
    try:
        import websocket
    except Exception:
        debug_log("WS", "websocket-client is not available; WS worker disabled")
        return

    debug_log("WS", "WS worker started")
    while not stop_event.is_set():
        server_url = settings_store.get_server_url()
        valid_server_url, server_url_error = validate_server_url(server_url)
        if server_url_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(server_url_error)
            debug_log("WS", f"Invalid server URL: {server_url_error}")
            time.sleep(1)
            continue
        valid_token, refresh_error = refresh_if_needed(settings_store, valid_server_url)
        if refresh_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(f"Token refresh failed: {refresh_error}")
            debug_log("WS", f"Token refresh failed: {refresh_error}")
            time.sleep(2)
            continue
        valid_token, token_error = validate_agent_token(valid_token)
        if token_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(token_error)
            debug_log("WS", f"Invalid token: {token_error}")
            time.sleep(1)
            continue

        ws = None
        force_reconnect_now = False
        shared_state.set_last_error("")
        try:
            ws_url = build_ws_url(valid_server_url, valid_token)
            debug_log("WS", f"Connecting to {build_ws_log_url(valid_server_url)}")
            ws = websocket.create_connection(ws_url, timeout=5)
            ws.settimeout(1)
            shared_state.set_ws_connected(True)
            debug_log("WS", "Connected")
            next_keepalive = time.time() + 15

            while not stop_event.is_set():
                if reconnect_event.is_set():
                    force_reconnect_now = True
                    debug_log("WS", "Reconnect signal received: restarting WebSocket session")
                    break

                if time.time() >= next_keepalive:
                    try:
                        ws.send("ping")
                    except Exception:
                        break
                    next_keepalive = time.time() + 15

                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception:
                    break

                if not raw:
                    continue

                try:
                    payload = json.loads(raw)
                except Exception:
                    continue

                msg_type = payload.get("type")
                if msg_type == "config_snapshot":
                    items = payload.get("items") or []
                    shared_state.set_config_items(items)
                    debug_log("WS", f"config_snapshot received: {len(items)} item(s)")
                elif msg_type == "commands_updated":
                    command_refresh_event.set()
                    debug_log("WS", "commands_updated received")

        except Exception as e:
            shared_state.set_last_error(str(e))
            debug_log("WS", f"Disconnected: {e}")
        finally:
            shared_state.set_ws_connected(False)
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
            debug_log("WS", "Connection closed")

        if not stop_event.is_set():
            if force_reconnect_now:
                reconnect_event.clear()
                debug_log("WS", "Reconnect requested: reconnecting immediately")
                continue
            if reconnect_event.is_set():
                reconnect_event.clear()
                debug_log("WS", "Reconnect requested: reconnecting immediately")
                continue
            time.sleep(WS_RECONNECT_DELAY_SECONDS)
            debug_log("WS", f"Reconnect in {WS_RECONNECT_DELAY_SECONDS}s")


def agent_worker(
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    manual_refresh_event: threading.Event,
    command_refresh_event: threading.Event,
    settings_store: SettingsStore,
    shared_state: SharedState,
) -> None:
    last_config_poll = 0.0
    last_ping = 0.0
    last_command_poll = 0.0

    debug_log("AGENT", "Agent worker started")
    while not stop_event.is_set():
        server_url = settings_store.get_server_url()
        valid_server_url, server_url_error = validate_server_url(server_url)
        if server_url_error:
            shared_state.set_last_error(server_url_error)
            debug_log("AGENT", f"Invalid server URL: {server_url_error}")
            time.sleep(1)
            continue
        valid_token, refresh_error = refresh_if_needed(settings_store, valid_server_url)
        if refresh_error:
            shared_state.set_last_error(f"Token refresh failed: {refresh_error}")
            debug_log("AGENT", f"Token refresh failed: {refresh_error}")
            time.sleep(2)
            continue
        valid_token, token_error = validate_agent_token(valid_token)
        if token_error:
            shared_state.set_last_error(token_error)
            debug_log("AGENT", f"Invalid token: {token_error}")
            time.sleep(1)
            continue

        now = time.time()
        force_manual_refresh = manual_refresh_event.is_set()
        if force_manual_refresh:
            manual_refresh_event.clear()
            debug_log("AGENT", "Manual refresh requested")

        if force_manual_refresh:
            config = get_agent_config(valid_server_url, valid_token)
            if config is not None:
                shared_state.set_config_items(config)
                debug_log("AGENT", f"Manual config refresh -> {len(config)} item(s)")
            run_command_processor(valid_server_url, valid_token)
            last_command_poll = now
            last_config_poll = now
        elif (not shared_state.is_ws_connected()) and (now - last_config_poll >= CONFIG_FALLBACK_POLL_SECONDS):
            config = get_agent_config(valid_server_url, valid_token)
            if config is not None:
                shared_state.set_config_items(config)
                debug_log("AGENT", f"Fallback config refresh -> {len(config)} item(s)")
            last_config_poll = now

        if now - last_ping >= PING_INTERVAL_SECONDS:
            check_processes_and_ping(valid_server_url, shared_state.get_config_items(), valid_token)
            last_ping = now

        if command_refresh_event.is_set() or (now - last_command_poll >= COMMAND_POLL_INTERVAL_SECONDS):
            command_refresh_event.clear()
            run_command_processor(valid_server_url, valid_token)
            last_command_poll = now

        if reconnect_event.is_set():
            reconnect_event.clear()

        time.sleep(1)


class SettingsUI:
    def __init__(
        self,
        settings_store: SettingsStore,
        shared_state: SharedState,
        debug_log_store: DebugLogStore,
        reconnect_event: threading.Event,
        manual_refresh_event: threading.Event,
        stop_event: threading.Event,
    ) -> None:
        self.settings_store = settings_store
        self.shared_state = shared_state
        self.debug_log_store = debug_log_store
        self.reconnect_event = reconnect_event
        self.manual_refresh_event = manual_refresh_event
        self.stop_event = stop_event
        self.ui_queue: "queue.Queue[str]" = queue.Queue()

        import tkinter as tk
        from tkinter import ttk, messagebox

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox

        self.root = tk.Tk()
        self.root.title("GameTracker Agent")
        self.root.geometry("900x640")
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        saved_token = self.settings_store.get_token()
        self.token_var = tk.StringVar(value="" if is_jwt_token(saved_token) else saved_token)
        self.server_url_var = tk.StringVar(value=self.settings_store.get_server_url())
        self.device_id_var = tk.StringVar(value=self.settings_store.get_device_id() or f"gt-{uuid.uuid4().hex[:20]}")
        self.device_name_var = tk.StringVar(value=self.settings_store.get_device_name() or default_device_name())
        self.show_token_var = tk.BooleanVar(value=False)
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled_windows())
        self.log_autoscroll_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Disconnected")
        self.log_cursor = 0

        self._build_layout()
        self.root.withdraw()
        self.root.after(500, self._poll)

    def _build_layout(self) -> None:
        root_frame = self.ttk.Frame(self.root, padding=10)
        root_frame.pack(fill="both", expand=True)
        notebook = self.ttk.Notebook(root_frame)
        notebook.pack(fill="both", expand=True)

        settings_tab = self.ttk.Frame(notebook, padding=12)
        logs_tab = self.ttk.Frame(notebook, padding=12)
        notebook.add(settings_tab, text="Настройки")
        notebook.add(logs_tab, text="Логи")

        frame = settings_tab

        token_label = self.ttk.Label(frame, text="Pair Code (6 digits)")
        token_label.pack(anchor="w")

        token_row = self.ttk.Frame(frame)
        token_row.pack(fill="x", pady=(4, 8))

        self.token_entry = self.ttk.Entry(token_row, textvariable=self.token_var, show="*", width=80)
        self.token_entry.pack(side="left", fill="x", expand=True)
        self._attach_context_menu(self.token_entry)

        self.ttk.Checkbutton(
            token_row,
            text="Show",
            variable=self.show_token_var,
            command=self._toggle_show_token,
        ).pack(side="left", padx=(8, 0))

        server_label = self.ttk.Label(frame, text="Server URL")
        server_label.pack(anchor="w")
        self.server_entry = self.ttk.Entry(frame, textvariable=self.server_url_var, width=80)
        self.server_entry.pack(fill="x", pady=(4, 8))
        self._attach_context_menu(self.server_entry)

        device_row = self.ttk.Frame(frame)
        device_row.pack(fill="x", pady=(0, 8))
        self.ttk.Label(device_row, text="Device ID").pack(side="left")
        self.device_id_entry = self.ttk.Entry(device_row, textvariable=self.device_id_var, width=38)
        self.device_id_entry.pack(side="left", padx=(8, 0))
        self._attach_context_menu(self.device_id_entry)
        self.ttk.Label(device_row, text="Device Name").pack(side="left", padx=(12, 0))
        self.device_name_entry = self.ttk.Entry(device_row, textvariable=self.device_name_var, width=28)
        self.device_name_entry.pack(side="left", padx=(8, 0))
        self._attach_context_menu(self.device_name_entry)

        buttons_row = self.ttk.Frame(frame)
        buttons_row.pack(fill="x", pady=(0, 10))
        self.ttk.Button(buttons_row, text="Save/Pair", command=self._save_token).pack(side="left")
        self.ttk.Button(buttons_row, text="Reconnect", command=self._reconnect).pack(side="left", padx=(8, 0))
        self.ttk.Button(buttons_row, text="Refresh", command=self._refresh_now).pack(side="left", padx=(8, 0))

        autostart_row = self.ttk.Frame(frame)
        autostart_row.pack(fill="x", pady=(0, 10))
        self.ttk.Checkbutton(
            autostart_row,
            text="Enable autostart on login",
            variable=self.autostart_var,
            command=self._toggle_autostart,
        ).pack(side="left")

        self.ttk.Label(frame, text="Tracked games").pack(anchor="w")
        self.games_box = self.tk.Text(frame, height=18, wrap="none")
        self.games_box.pack(fill="both", expand=True, pady=(4, 8))
        self.games_box.bind("<Key>", self._readonly_text_keypress)
        self._attach_context_menu(self.games_box)

        self.ttk.Label(frame, textvariable=self.status_var).pack(anchor="w")

        logs_tools = self.ttk.Frame(logs_tab)
        logs_tools.pack(fill="x", pady=(0, 8))
        self.ttk.Button(logs_tools, text="Очистить", command=self._clear_logs).pack(side="left")
        self.ttk.Checkbutton(
            logs_tools,
            text="Автопрокрутка",
            variable=self.log_autoscroll_var,
        ).pack(side="left", padx=(10, 0))

        logs_area = self.ttk.Frame(logs_tab)
        logs_area.pack(fill="both", expand=True)
        self.logs_box = self.tk.Text(logs_area, wrap="none")
        self.logs_box.pack(side="left", fill="both", expand=True)
        self.logs_box.bind("<Key>", self._readonly_text_keypress)
        self._attach_context_menu(self.logs_box)
        logs_scrollbar = self.ttk.Scrollbar(logs_area, orient="vertical", command=self.logs_box.yview)
        logs_scrollbar.pack(side="right", fill="y")
        self.logs_box.configure(yscrollcommand=logs_scrollbar.set)

    def _toggle_show_token(self) -> None:
        self.token_entry.configure(show="" if self.show_token_var.get() else "*")

    def _readonly_text_keypress(self, event) -> str:
        if (event.state & 0x4) and event.keysym.lower() in {"c", "a"}:
            return ""
        return "break"

    def _attach_context_menu(self, widget) -> None:
        widget.bind("<Button-3>", self._show_context_menu, add="+")
        widget.bind("<Button-2>", self._show_context_menu, add="+")

    def _show_context_menu(self, event):
        widget = event.widget
        if not isinstance(widget, (self.tk.Entry, self.ttk.Entry, self.tk.Text)):
            return None

        menu = self.tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        if isinstance(widget, (self.tk.Entry, self.ttk.Entry)):
            menu.add_command(label="Выделить всё", command=lambda: widget.selection_range(0, "end"))
        else:
            menu.add_command(label="Выделить всё", command=lambda: widget.tag_add("sel", "1.0", "end-1c"))

        if widget is self.games_box or widget is self.logs_box:
            menu.entryconfigure("Вырезать", state="disabled")
            menu.entryconfigure("Вставить", state="disabled")

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _save_token(self) -> None:
        token = self.token_var.get().strip()
        server_url = self.server_url_var.get().strip()
        valid_server_url, server_url_error = validate_server_url(server_url)
        if server_url_error:
            debug_log("UI", f"Save/Pair rejected: invalid server URL ({server_url_error})")
            self.messagebox.showerror("Server URL", f"Invalid server URL: {server_url_error}")
            return
        device_id = self.device_id_var.get().strip()
        if not device_id:
            device_id = f"gt-{uuid.uuid4().hex[:20]}"
            self.device_id_var.set(device_id)
        device_name = self.device_name_var.get().strip() or default_device_name()

        if token and PAIR_CODE_RE.fullmatch(token):
            debug_log("UI", f"Pair requested for device_id={device_id}")
            payload, err = pair_agent_device(valid_server_url, token, device_id, device_name)
            if err:
                debug_log("UI", f"Pair failed: {err}")
                self.messagebox.showerror("Pairing", f"Pair failed: {err}")
                return
            apply_agent_auth_payload(self.settings_store, payload or {})
            self.token_var.set("")
            self.server_url_var.set(valid_server_url)
            self.device_id_var.set(self.settings_store.get_device_id())
            self.device_name_var.set(self.settings_store.get_device_name() or device_name)
            self.reconnect_event.set()
            debug_log("UI", "Pair success; reconnect requested")
            self.messagebox.showinfo("Pairing", "Device paired successfully.")
            return

        if token:
            debug_log("UI", "Save/Pair rejected: non-empty token is not a 6-digit pair code")
            self.messagebox.showerror("Pairing", "Enter 6-digit pair code from web settings.")
            return
        self.settings_store.set_server_url(valid_server_url)
        self.settings_store.set_device_id(device_id)
        self.settings_store.set_device_name(device_name)
        self.settings_store.save()
        self.reconnect_event.set()
        debug_log("UI", f"Settings saved; reconnect requested for {valid_server_url}")

    def _toggle_autostart(self) -> None:
        desired = bool(self.autostart_var.get())
        ok, err = set_autostart_windows(desired)
        if not ok:
            self.autostart_var.set(not desired)
            debug_log("UI", f"Autostart change failed: {err}")
            self.messagebox.showerror("Autostart", err)
            return
        self.settings_store.set_autostart(desired)
        self.settings_store.save()
        debug_log("UI", f"Autostart set to {desired}")

    def _refresh_now(self) -> None:
        self.manual_refresh_event.set()
        debug_log("UI", "Refresh requested (manual config+commands refresh)")

    def _reconnect(self) -> None:
        self.reconnect_event.set()
        debug_log("UI", "Reconnect requested")

    def _render_games(self) -> None:
        items = self.shared_state.get_config_items()
        lines = []
        for item in items:
            enabled = "ON" if item.get("enabled", True) else "OFF"
            lines.append(
                f"[{enabled}] {item.get('title') or 'Untitled'} | {item.get('exe_name') or '-'} | "
                f"{item.get('launch_path') or '-'}"
            )
        text = "\n".join(lines) if lines else "No synced games"
        self.games_box.delete("1.0", "end")
        self.games_box.insert("1.0", text)

    def _render_logs(self) -> None:
        next_cursor, lines = self.debug_log_store.read_since(self.log_cursor)
        self.log_cursor = next_cursor
        if not lines:
            return
        self.logs_box.insert("end", "\n".join(lines) + "\n")
        if self.log_autoscroll_var.get():
            self.logs_box.see("end")

    def _clear_logs(self) -> None:
        self.logs_box.delete("1.0", "end")
        self.log_cursor = self.debug_log_store.clear()
        debug_log("UI", "Logs cleared from GUI")

    def _poll(self) -> None:
        if self.stop_event.is_set():
            self.root.quit()
            return

        while True:
            try:
                cmd = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if cmd == "show":
                self.show()

        ws_text = "Connected via WebSocket" if self.shared_state.is_ws_connected() else "Disconnected"
        err = self.shared_state.get_last_error()
        if err:
            ws_text = f"{ws_text} | {err}"
        self.status_var.set(ws_text)
        self._render_games()
        self._render_logs()
        self.root.after(1000, self._poll)

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        debug_log("UI", "Window shown")

    def hide(self) -> None:
        self.root.withdraw()
        debug_log("UI", "Window hidden")

    def request_show(self) -> None:
        self.ui_queue.put("show")
        debug_log("UI", "Show requested from tray")


def create_icon():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), color="#10b981")
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 20, 56, 44], fill="#059669")
    draw.rectangle([16, 28, 24, 36], fill="#34d399")
    draw.rectangle([40, 28, 48, 36], fill="#34d399")
    return img


def tray_worker(settings_ui: SettingsUI, reconnect_event: threading.Event, stop_event: threading.Event) -> None:
    try:
        import pystray
        from pystray import MenuItem as Item
    except Exception:
        debug_log("TRAY", "pystray is not available; tray worker disabled")
        return

    icon_ref: Dict[str, Optional[object]] = {"icon": None}

    def on_open(_icon, _item):
        settings_ui.request_show()

    def on_reconnect(_icon, _item):
        reconnect_event.set()
        debug_log("TRAY", "Reconnect clicked")

    def on_exit(icon, _item):
        stop_event.set()
        debug_log("TRAY", "Exit clicked")
        try:
            icon.stop()
        except Exception:
            pass
        settings_ui.root.after(50, settings_ui.root.quit)

    menu = pystray.Menu(
        Item("Настройки", on_open),
        Item("Переподключить", on_reconnect),
        Item("Выход", on_exit),
    )

    icon = pystray.Icon("GameTrackerAgent", create_icon(), "GameTracker Agent", menu)
    icon_ref["icon"] = icon
    debug_log("TRAY", "Tray icon started")
    icon.run()


def main() -> None:
    debug_store = DebugLogStore()
    set_debug_log_store(debug_store)
    debug_log("SYSTEM", "Agent starting")

    stop_event = threading.Event()
    reconnect_event = threading.Event()
    manual_refresh_event = threading.Event()
    command_refresh_event = threading.Event()

    settings_store = SettingsStore()
    settings_store.load()
    debug_log("SYSTEM", "Settings loaded")
    if not settings_store.get_device_id():
        settings_store.set_device_id(f"gt-{uuid.uuid4().hex[:20]}")
    if not settings_store.get_device_name():
        settings_store.set_device_name(default_device_name())
    settings_store.save()

    # Sync UI state with actual autostart registry value at startup.
    if os.name == "nt":
        settings_store.set_autostart(is_autostart_enabled_windows())
        settings_store.save()

    shared_state = SharedState()
    settings_ui = SettingsUI(
        settings_store,
        shared_state,
        debug_store,
        reconnect_event,
        manual_refresh_event,
        stop_event,
    )

    ws_thread = threading.Thread(
        target=ws_worker,
        args=(stop_event, reconnect_event, command_refresh_event, settings_store, shared_state),
        daemon=True,
    )
    ws_thread.start()
    debug_log("SYSTEM", "WS thread started")

    agent_thread = threading.Thread(
        target=agent_worker,
        args=(stop_event, reconnect_event, manual_refresh_event, command_refresh_event, settings_store, shared_state),
        daemon=True,
    )
    agent_thread.start()
    debug_log("SYSTEM", "Agent thread started")

    tray_thread = threading.Thread(
        target=tray_worker,
        args=(settings_ui, reconnect_event, stop_event),
        daemon=True,
    )
    tray_thread.start()
    debug_log("SYSTEM", "Tray thread started")

    _, token_error = validate_agent_token(settings_store.get_token())
    _, server_url_error = validate_server_url(settings_store.get_server_url())
    if token_error or server_url_error:
        settings_ui.show()
        debug_log("SYSTEM", f"Showing UI because config is incomplete (token_error={bool(token_error)}, server_url_error={bool(server_url_error)})")

    try:
        settings_ui.root.mainloop()
    finally:
        stop_event.set()
        debug_log("SYSTEM", "Shutdown requested")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
