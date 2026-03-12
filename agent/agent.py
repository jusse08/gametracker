import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import psutil
import requests

APP_NAME = "GameTracker"
AGENT_SETTINGS_FILENAME = "agent_settings.json"
AGENT_TOKEN_FILENAME = "agent_token.bin"

PING_INTERVAL_SECONDS = 30
COMMAND_POLL_INTERVAL_SECONDS = 6
CONFIG_FALLBACK_POLL_SECONDS = 60
WS_RECONNECT_DELAY_SECONDS = 3
TOKEN_ALLOWED_RE = re.compile(r"^[A-Za-z0-9_-]+$")
WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:\\")


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
    if not TOKEN_ALLOWED_RE.fullmatch(token):
        return "", "token contains unsupported characters"
    if len(token) < 16:
        return "", "token is too short"
    return token, None


def validate_server_url(raw_url: str) -> Tuple[str, Optional[str]]:
    url = (raw_url or "").strip().rstrip("/")
    if not url:
        return "", "empty server url"
    if not (url.startswith("http://") or url.startswith("https://")):
        return "", "server url must start with http:// or https://"
    return url, None


def validate_launch_path(launch_path: str) -> Tuple[bool, Optional[str]]:
    path = (launch_path or "").strip().strip('"')
    if not path:
        return False, "empty launch_path"
    if path.startswith("\\\\"):
        return False, "UNC path is not allowed"
    if not WINDOWS_ABS_PATH_RE.match(path):
        return False, "path must be absolute Windows path"
    if not path.lower().endswith(".exe"):
        return False, "path must point to .exe"
    return True, None


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
        self._autostart = False
        self._server_url = ""

    def load(self) -> None:
        os.makedirs(get_storage_dir(), exist_ok=True)
        token = ""
        token_path = get_token_path()
        if os.path.exists(token_path):
            try:
                with open(token_path, "rb") as f:
                    token = decrypt_for_current_user(f.read()).decode("utf-8").strip()
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
            self._autostart = autostart
            self._server_url = server_url

    def save(self) -> None:
        with self._lock:
            token = self._token
            autostart = self._autostart
            server_url = self._server_url
        os.makedirs(get_storage_dir(), exist_ok=True)
        try:
            with open(get_token_path(), "wb") as f:
                f.write(encrypt_for_current_user(token.encode("utf-8")))
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
    return {"X-Agent-Token": token}


def build_ws_url(server_url: str, agent_token: str) -> str:
    ws_scheme = "wss" if server_url.startswith("https://") else "ws"
    host = server_url.split("://", 1)[-1]
    return f"{ws_scheme}://{host}/api/agent/ws?token={quote(agent_token)}"


def get_agent_config(server_url: str, agent_token: str) -> Optional[List[Dict]]:
    try:
        response = requests.get(
            f"{server_url}/api/agent/config",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("items", [])
    except Exception:
        return None


def get_pending_commands(server_url: str, agent_token: str) -> List[Dict]:
    try:
        response = requests.get(
            f"{server_url}/api/agent/commands",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("items", [])
    except Exception:
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
    except Exception:
        pass


def rotate_token_self(server_url: str, agent_token: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        response = requests.post(
            f"{server_url}/api/agent/token/rotate/self",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        token = response.json().get("agent_token", "").strip()
        valid, err = validate_agent_token(token)
        if err:
            return None, err
        return valid, None
    except Exception as e:
        return None, str(e)


def launch_game(launch_path: str) -> Tuple[bool, Optional[str]]:
    ok, err = validate_launch_path(launch_path)
    if not ok:
        return False, err
    try:
        if os.name == "nt":
            os.startfile(launch_path)
        else:
            subprocess.Popen([launch_path])
        return True, None
    except Exception as e:
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
        return True
    except Exception:
        return False


def run_command_processor(server_url: str, agent_token: str) -> None:
    for command in get_pending_commands(server_url, agent_token):
        game_id = command.get("game_id")
        request_id = command.get("request_id")
        launch_path = (command.get("launch_path") or "").strip()
        if not game_id or not request_id or not launch_path:
            continue
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
    return pinged


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
        return

    while not stop_event.is_set():
        token = settings_store.get_token()
        server_url = settings_store.get_server_url()
        valid_server_url, server_url_error = validate_server_url(server_url)
        if server_url_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(server_url_error)
            time.sleep(1)
            continue
        valid_token, token_error = validate_agent_token(token)
        if token_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(token_error)
            time.sleep(1)
            continue

        ws = None
        shared_state.set_last_error("")
        try:
            ws = websocket.create_connection(build_ws_url(valid_server_url, valid_token), timeout=5)
            ws.settimeout(1)
            shared_state.set_ws_connected(True)
            next_keepalive = time.time() + 15

            while not stop_event.is_set():
                if reconnect_event.is_set():
                    reconnect_event.clear()
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
                    shared_state.set_config_items(payload.get("items") or [])
                elif msg_type == "commands_updated":
                    command_refresh_event.set()

        except Exception as e:
            shared_state.set_last_error(str(e))
        finally:
            shared_state.set_ws_connected(False)
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

        if not stop_event.is_set():
            time.sleep(WS_RECONNECT_DELAY_SECONDS)


def agent_worker(
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    command_refresh_event: threading.Event,
    settings_store: SettingsStore,
    shared_state: SharedState,
) -> None:
    last_config_poll = 0.0
    last_ping = 0.0
    last_command_poll = 0.0

    while not stop_event.is_set():
        token = settings_store.get_token()
        server_url = settings_store.get_server_url()
        valid_server_url, server_url_error = validate_server_url(server_url)
        if server_url_error:
            shared_state.set_last_error(server_url_error)
            time.sleep(1)
            continue
        valid_token, token_error = validate_agent_token(token)
        if token_error:
            shared_state.set_last_error(token_error)
            time.sleep(1)
            continue

        now = time.time()

        if (not shared_state.is_ws_connected()) and (now - last_config_poll >= CONFIG_FALLBACK_POLL_SECONDS):
            config = get_agent_config(valid_server_url, valid_token)
            if config is not None:
                shared_state.set_config_items(config)
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
        reconnect_event: threading.Event,
        stop_event: threading.Event,
    ) -> None:
        self.settings_store = settings_store
        self.shared_state = shared_state
        self.reconnect_event = reconnect_event
        self.stop_event = stop_event
        self.ui_queue: "queue.Queue[str]" = queue.Queue()

        import tkinter as tk
        from tkinter import ttk, messagebox

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox

        self.root = tk.Tk()
        self.root.title("GameTracker Agent")
        self.root.geometry("760x520")
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        self.token_var = tk.StringVar(value=self.settings_store.get_token())
        self.server_url_var = tk.StringVar(value=self.settings_store.get_server_url())
        self.show_token_var = tk.BooleanVar(value=False)
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled_windows())
        self.status_var = tk.StringVar(value="Disconnected")

        self._build_layout()
        self.root.withdraw()
        self.root.after(500, self._poll)

    def _build_layout(self) -> None:
        frame = self.ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        token_label = self.ttk.Label(frame, text="Agent Token")
        token_label.pack(anchor="w")

        token_row = self.ttk.Frame(frame)
        token_row.pack(fill="x", pady=(4, 8))

        self.token_entry = self.ttk.Entry(token_row, textvariable=self.token_var, show="*", width=80)
        self.token_entry.pack(side="left", fill="x", expand=True)

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

        buttons_row = self.ttk.Frame(frame)
        buttons_row.pack(fill="x", pady=(0, 10))
        self.ttk.Button(buttons_row, text="Save Token", command=self._save_token).pack(side="left")
        self.ttk.Button(buttons_row, text="Rotate Token", command=self._rotate_token).pack(side="left", padx=(8, 0))
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
        self.games_box.configure(state="disabled")

        self.ttk.Label(frame, textvariable=self.status_var).pack(anchor="w")

    def _toggle_show_token(self) -> None:
        self.token_entry.configure(show="" if self.show_token_var.get() else "*")

    def _save_token(self) -> None:
        token = self.token_var.get().strip()
        server_url = self.server_url_var.get().strip()
        valid_server_url, server_url_error = validate_server_url(server_url)
        if server_url_error:
            self.messagebox.showerror("Server URL", f"Invalid server URL: {server_url_error}")
            return
        if token:
            valid, err = validate_agent_token(token)
            if err:
                self.messagebox.showerror("Token", f"Invalid token: {err}")
                return
            token = valid
        self.settings_store.set_server_url(valid_server_url)
        self.settings_store.set_token(token)
        self.settings_store.save()
        self.reconnect_event.set()

    def _rotate_token(self) -> None:
        current = self.token_var.get().strip() or self.settings_store.get_token().strip()
        valid, err = validate_agent_token(current)
        if err:
            self.messagebox.showerror("Token", f"Invalid token: {err}")
            return

        server_url, server_url_error = validate_server_url(self.server_url_var.get())
        if server_url_error:
            self.messagebox.showerror("Server URL", f"Invalid server URL: {server_url_error}")
            return

        token, rotate_error = rotate_token_self(server_url, valid)
        if rotate_error:
            self.messagebox.showerror("Token", f"Rotate failed: {rotate_error}")
            return

        self.token_var.set(token or "")
        self.settings_store.set_server_url(server_url)
        self.settings_store.set_token(token or "")
        self.settings_store.save()
        self.reconnect_event.set()

    def _toggle_autostart(self) -> None:
        desired = bool(self.autostart_var.get())
        ok, err = set_autostart_windows(desired)
        if not ok:
            self.autostart_var.set(not desired)
            self.messagebox.showerror("Autostart", err)
            return
        self.settings_store.set_autostart(desired)
        self.settings_store.save()

    def _refresh_now(self) -> None:
        self.reconnect_event.set()

    def _reconnect(self) -> None:
        self.reconnect_event.set()

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
        self.games_box.configure(state="normal")
        self.games_box.delete("1.0", "end")
        self.games_box.insert("1.0", text)
        self.games_box.configure(state="disabled")

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
        self.root.after(1000, self._poll)

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()

    def request_show(self) -> None:
        self.ui_queue.put("show")


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
        return

    icon_ref: Dict[str, Optional[object]] = {"icon": None}

    def on_open(_icon, _item):
        settings_ui.request_show()

    def on_reconnect(_icon, _item):
        reconnect_event.set()

    def on_exit(icon, _item):
        stop_event.set()
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
    icon.run()


def main() -> None:
    stop_event = threading.Event()
    reconnect_event = threading.Event()
    command_refresh_event = threading.Event()

    settings_store = SettingsStore()
    settings_store.load()

    # Sync UI state with actual autostart registry value at startup.
    if os.name == "nt":
        settings_store.set_autostart(is_autostart_enabled_windows())
        settings_store.save()

    shared_state = SharedState()
    settings_ui = SettingsUI(settings_store, shared_state, reconnect_event, stop_event)

    ws_thread = threading.Thread(
        target=ws_worker,
        args=(stop_event, reconnect_event, command_refresh_event, settings_store, shared_state),
        daemon=True,
    )
    ws_thread.start()

    agent_thread = threading.Thread(
        target=agent_worker,
        args=(stop_event, reconnect_event, command_refresh_event, settings_store, shared_state),
        daemon=True,
    )
    agent_thread.start()

    tray_thread = threading.Thread(
        target=tray_worker,
        args=(settings_ui, reconnect_event, stop_event),
        daemon=True,
    )
    tray_thread.start()

    _, token_error = validate_agent_token(settings_store.get_token())
    _, server_url_error = validate_server_url(settings_store.get_server_url())
    if token_error or server_url_error:
        settings_ui.show()

    try:
        settings_ui.root.mainloop()
    finally:
        stop_event.set()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
