import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Optional, Tuple

import api_client as net_api
import auth_flow
from runtime_state import ProcessTargetWatcher, SharedState
from storage import SettingsStore
from ui import SettingsUI
import workers

PING_INTERVAL_SECONDS = 10
COMMAND_POLL_INTERVAL_SECONDS = 6
COMMAND_WATCHDOG_INTERVAL_SECONDS = 90
CONFIG_FALLBACK_POLL_SECONDS = 5
WS_RECONNECT_DELAY_SECONDS = 3
WS_RECONNECT_MAX_DELAY_SECONDS = 30
PROCESS_FULL_SCAN_INTERVAL_SECONDS = 20
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


def get_agent_headers(agent_token: str) -> Dict[str, str]:
    token, err = validate_agent_token(agent_token)
    if err:
        raise ValueError(f"Invalid agent token: {err}")
    return {"Authorization": f"Bearer {token}"}


def build_ws_url(server_url: str, agent_token: str) -> str:
    return net_api.build_ws_url(server_url, agent_token)


def build_ws_log_url(server_url: str) -> str:
    return net_api.build_ws_log_url(server_url)


def get_agent_config(server_url: str, agent_token: str) -> Optional[List[Dict]]:
    return net_api.get_agent_config(server_url, get_agent_headers(agent_token), debug_log)


def get_pending_commands(server_url: str, agent_token: str) -> List[Dict]:
    return net_api.get_pending_commands(server_url, get_agent_headers(agent_token), debug_log)


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
    net_api.ack_command(server_url, payload, get_agent_headers(agent_token), debug_log)


def pair_agent_device(
    server_url: str,
    pair_code: str,
    device_id: str,
    device_name: str,
) -> Tuple[Optional[Dict], Optional[str]]:
    return net_api.pair_agent_device(server_url, pair_code, device_id, device_name, debug_log)


def refresh_agent_token(server_url: str, device_id: str, refresh_token: str) -> Tuple[Optional[Dict], Optional[str]]:
    return net_api.refresh_agent_token(server_url, device_id, refresh_token, debug_log)


def update_agent_device_name(server_url: str, agent_token: str, device_name: str) -> Optional[str]:
    return net_api.update_agent_device_name(server_url, device_name, get_agent_headers(agent_token), debug_log)


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
    return net_api.ping_server(server_url, game_id, exe_name, get_agent_headers(agent_token), debug_log)


def run_command_processor(
    server_url: str,
    agent_token: str,
    handled_requests: Optional[workers.HandledRequests] = None,
) -> Tuple[int, int]:
    return workers.run_command_processor(
        server_url=server_url,
        agent_token=agent_token,
        get_pending_commands_fn=get_pending_commands,
        launch_game_fn=launch_game,
        ack_command_fn=ack_command,
        debug_log_fn=debug_log,
        handled_requests=handled_requests,
    )


def build_unique_exe_targets(config_items: List[Dict]) -> Dict[str, int]:
    return workers.build_unique_exe_targets(config_items)


def check_processes_and_ping(
    server_url: str,
    config_items: List[Dict],
    agent_token: str,
    watcher: Optional[ProcessTargetWatcher] = None,
) -> Tuple[int, int]:
    return workers.check_processes_and_ping(
        server_url=server_url,
        config_items=config_items,
        agent_token=agent_token,
        ping_server_fn=ping_server,
        watcher=watcher or ProcessTargetWatcher(full_scan_interval_seconds=PROCESS_FULL_SCAN_INTERVAL_SECONDS),
        debug_log_fn=debug_log,
    )


def default_device_name() -> str:
    host = os.getenv("COMPUTERNAME") or os.getenv("HOSTNAME") or "Agent-PC"
    return f"GameTracker Agent ({host})"


def apply_agent_auth_payload(settings_store: SettingsStore, payload: Dict) -> None:
    auth_flow.apply_agent_auth_payload(settings_store, payload)


def refresh_if_needed(settings_store: SettingsStore, server_url: str, force: bool = False) -> Tuple[str, Optional[str]]:
    return auth_flow.refresh_if_needed(
        settings_store=settings_store,
        server_url=server_url,
        refresh_call=refresh_agent_token,
        is_jwt_token=is_jwt_token,
        log=debug_log,
        force=force,
    )


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
    workers.ws_worker(
        stop_event=stop_event,
        reconnect_event=reconnect_event,
        command_refresh_event=command_refresh_event,
        settings_store=settings_store,
        shared_state=shared_state,
        websocket_module=websocket,
        validate_server_url_fn=validate_server_url,
        refresh_if_needed_fn=refresh_if_needed,
        validate_agent_token_fn=validate_agent_token,
        build_ws_url_fn=build_ws_url,
        build_ws_log_url_fn=build_ws_log_url,
        debug_log_fn=debug_log,
        ws_reconnect_delay_seconds=WS_RECONNECT_DELAY_SECONDS,
        ws_reconnect_max_delay_seconds=WS_RECONNECT_MAX_DELAY_SECONDS,
    )


def agent_worker(
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    manual_refresh_event: threading.Event,
    command_refresh_event: threading.Event,
    settings_store: SettingsStore,
    shared_state: SharedState,
) -> None:
    process_watcher = ProcessTargetWatcher(full_scan_interval_seconds=PROCESS_FULL_SCAN_INTERVAL_SECONDS)
    workers.agent_worker(
        stop_event=stop_event,
        reconnect_event=reconnect_event,
        manual_refresh_event=manual_refresh_event,
        command_refresh_event=command_refresh_event,
        settings_store=settings_store,
        shared_state=shared_state,
        validate_server_url_fn=validate_server_url,
        refresh_if_needed_fn=refresh_if_needed,
        validate_agent_token_fn=validate_agent_token,
        get_agent_config_fn=get_agent_config,
        run_command_processor_fn=run_command_processor,
        check_processes_and_ping_fn=check_processes_and_ping,
        process_watcher=process_watcher,
        debug_log_fn=debug_log,
        config_fallback_poll_seconds=CONFIG_FALLBACK_POLL_SECONDS,
        ping_interval_seconds=PING_INTERVAL_SECONDS,
        command_poll_interval_seconds=COMMAND_POLL_INTERVAL_SECONDS,
        command_watchdog_interval_seconds=COMMAND_WATCHDOG_INTERVAL_SECONDS,
    )


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
        pair_code_re=PAIR_CODE_RE,
        is_jwt_token_fn=is_jwt_token,
        default_device_name_fn=default_device_name,
        is_autostart_enabled_windows_fn=is_autostart_enabled_windows,
        validate_server_url_fn=validate_server_url,
        pair_agent_device_fn=pair_agent_device,
        apply_agent_auth_payload_fn=apply_agent_auth_payload,
        update_agent_device_name_fn=update_agent_device_name,
        set_autostart_windows_fn=set_autostart_windows,
        debug_log_fn=debug_log,
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

    _, token_error = validate_agent_token(settings_store.get_token())
    _, server_url_error = validate_server_url(settings_store.get_server_url())
    if token_error or server_url_error:
        settings_ui.show()
        debug_log("SYSTEM", f"Showing UI because config is incomplete (token_error={bool(token_error)}, server_url_error={bool(server_url_error)})")

    try:
        settings_ui.run()
    finally:
        stop_event.set()
        debug_log("SYSTEM", "Shutdown requested")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
