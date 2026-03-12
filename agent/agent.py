import os
import builtins
import ctypes
import queue
import re
import subprocess
import sys
import tempfile
import time
import threading
import traceback
from ctypes import wintypes
from datetime import datetime

AGENT_CODE_VERSION = "2026.03.12-overlay-debug-1"
TOKEN_ALLOWED_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _get_bootstrap_log_paths():
    temp_log = os.path.join(tempfile.gettempdir(), "gametracker-agent-bootstrap.log")
    cwd_log = os.path.abspath("gametracker-agent-bootstrap.log")
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        exe_log = os.path.join(exe_dir, "gametracker-agent-bootstrap.log")
    else:
        exe_log = os.path.abspath("gametracker-agent-bootstrap.log")

    paths = []
    for path in (temp_log, cwd_log, exe_log):
        if path and path not in paths:
            paths.append(path)
    return paths


def _bootstrap_log(message):
    line = f"[{datetime.now()}] {message}"
    for path in _BOOTSTRAP_LOG_PATHS:
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


_BOOTSTRAP_LOG_PATHS = _get_bootstrap_log_paths()
_bootstrap_log(
    "Bootstrap start: "
    f"version={AGENT_CODE_VERSION}, pid={os.getpid()}, cwd={os.getcwd()}, "
    f"argv={sys.argv}, executable={sys.executable}"
)

try:
    import psutil
    import requests
except Exception:
    _bootstrap_log("FATAL: dependency import failed:\n" + traceback.format_exc())
    raise

# Server URL
SERVER_URL = os.getenv("GAMETRACKER_SERVER_URL", "http://localhost:8000").strip().rstrip("/")
APP_NAME = "GameTracker"
AGENT_TOKEN_FILENAME = "agent_token.bin"

# How often to check the config and how often to ping the server
CONFIG_POLL_INTERVAL_SECONDS = 300  # 5 minutes
CONFIG_RETRY_INTERVAL_SECONDS = 10  # retry faster on empty/error config, but avoid 1s spam
PING_INTERVAL_SECONDS = 30          # 30 seconds
COMMAND_POLL_INTERVAL_SECONDS = 3   # 3 seconds
FOCUS_POLL_INTERVAL_SECONDS = 1      # 1 second
OVERLAY_SHOW_WHEN_NO_MATCH = os.getenv("GAMETRACKER_OVERLAY_SHOW_NO_MATCH", "1").strip() != "0"

_ORIGINAL_PRINT = builtins.print
_LOG_LOCK = threading.Lock()
_PRINT_HOOK_INSTALLED = False


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _bytes_to_blob(data):
    if not data:
        return DATA_BLOB(0, None)
    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))


def _blob_to_bytes(blob):
    if not blob.cbData or not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def get_storage_dir():
    if os.name == "nt":
        base = os.getenv("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".config", "gametracker")


def get_agent_token_path():
    return os.path.join(get_storage_dir(), AGENT_TOKEN_FILENAME)


def get_agent_log_path():
    return os.path.join(get_storage_dir(), "agent.log")


def get_agent_log_paths():
    primary = get_agent_log_path()
    cwd_fallback = os.path.abspath("agent.log")
    temp_fallback = os.path.join(tempfile.gettempdir(), "gametracker-agent.log")
    paths = []
    for path in tuple(_BOOTSTRAP_LOG_PATHS) + (primary, cwd_fallback, temp_fallback):
        if path and path not in paths:
            paths.append(path)
    return paths


def _append_log_line(line):
    with _LOG_LOCK:
        for path in get_agent_log_paths():
            try:
                directory = os.path.dirname(path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass


def _install_print_hook():
    global _PRINT_HOOK_INSTALLED
    if _PRINT_HOOK_INSTALLED:
        return

    def _print_proxy(*args, **kwargs):
        _ORIGINAL_PRINT(*args, **kwargs)
        sep = kwargs.get("sep", " ")
        text = sep.join(str(arg) for arg in args)
        if text:
            _append_log_line(f"[{datetime.now()}] PRINT: {text}")

    builtins.print = _print_proxy
    _PRINT_HOOK_INSTALLED = True


def log_event(message):
    line = f"[{datetime.now()}] {message}"
    _ORIGINAL_PRINT(line)
    _append_log_line(line)


_install_print_hook()
log_event(
    "Logger bootstrap: "
    f"version={AGENT_CODE_VERSION}, pid={os.getpid()}, executable={sys.executable}, "
    f"argv={sys.argv}, server_url={SERVER_URL}, "
    f"bootstrap_log_paths={_BOOTSTRAP_LOG_PATHS}, log_paths={get_agent_log_paths()}"
)


def write_startup_markers():
    marker = (
        f"started_at={datetime.now().isoformat()}\n"
        f"pid={os.getpid()}\n"
        f"exe={sys.executable}\n"
        f"argv={sys.argv}\n"
    )
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        exe_marker = os.path.join(exe_dir, "gametracker-agent-startup.txt")
    else:
        exe_marker = os.path.abspath("gametracker-agent-startup.txt")

    paths = [
        os.path.join(tempfile.gettempdir(), "gametracker-agent-startup.txt"),
        os.path.abspath("gametracker-agent-startup.txt"),
        exe_marker,
    ]
    for path in paths:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(marker)
        except Exception:
            pass


def encrypt_for_current_user(raw_data):
    if os.name != "nt":
        return raw_data
    in_blob = _bytes_to_blob(raw_data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return _blob_to_bytes(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def decrypt_for_current_user(encrypted_data):
    if os.name != "nt":
        return encrypted_data
    in_blob = _bytes_to_blob(encrypted_data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return _blob_to_bytes(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def save_agent_token(token):
    try:
        os.makedirs(get_storage_dir(), exist_ok=True)
        token_bytes = token.strip().encode("utf-8")
        encrypted = encrypt_for_current_user(token_bytes)
        with open(get_agent_token_path(), "wb") as f:
            f.write(encrypted)
    except Exception as e:
        print(f"[{datetime.now()}] Warning: could not persist agent token: {e}")


def validate_agent_token(raw_token):
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


def load_agent_token():
    env_token = os.getenv("GAMETRACKER_AGENT_TOKEN", "").strip()
    if env_token:
        valid_token, token_error = validate_agent_token(env_token)
        if token_error:
            log_event(f"Invalid GAMETRACKER_AGENT_TOKEN: {token_error}")
            return ""
        return valid_token

    token_path = get_agent_token_path()
    if os.path.exists(token_path):
        try:
            with open(token_path, "rb") as f:
                encrypted_data = f.read()
                decrypted_data = decrypt_for_current_user(encrypted_data)
                file_token = decrypted_data.decode("utf-8").strip()
                if file_token:
                    valid_token, token_error = validate_agent_token(file_token)
                    if token_error:
                        log_event(f"Invalid token in {token_path}: {token_error}")
                        return ""
                    return valid_token
        except Exception as e:
            print(f"[{datetime.now()}] Warning: could not read token file: {e}")

    return ""


def ensure_agent_token():
    token = load_agent_token()
    if token:
        return token

    if not (sys.stdin and sys.stdin.isatty()):
        log_event(
            "Agent token not found and stdin is non-interactive. "
            "Set GAMETRACKER_AGENT_TOKEN or save token via interactive run."
        )
        return ""

    print("Agent token not found.")
    print("Open site settings and copy Agent Token, then paste it here.")
    entered = input("Agent token: ").strip()
    if not entered:
        return ""

    valid_token, token_error = validate_agent_token(entered)
    if token_error:
        log_event(f"Entered agent token is invalid: {token_error}")
        return ""

    save_agent_token(valid_token)
    return valid_token


def get_agent_headers(agent_token):
    valid_token, token_error = validate_agent_token(agent_token)
    if token_error:
        raise ValueError(f"Agent token is invalid: {token_error}")
    return {"X-Agent-Token": valid_token}


def get_foreground_exe_name():
    if os.name != "nt":
        return None

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not process_handle:
        return None

    try:
        image_len = wintypes.DWORD(1024)
        image_path = ctypes.create_unicode_buffer(1024)
        if not kernel32.QueryFullProcessImageNameW(process_handle, 0, image_path, ctypes.byref(image_len)):
            return None
        exe_name = os.path.basename(image_path.value).strip().lower()
        return exe_name or None
    finally:
        kernel32.CloseHandle(process_handle)


def get_focused_game(active_config):
    detected_exe_name = get_foreground_exe_name()
    if not detected_exe_name:
        return None, None, None

    if not active_config:
        return None, None, detected_exe_name

    for item in active_config:
        cfg_exe = (item.get("exe_name") or "").strip().lower()
        game_id = item.get("game_id")
        if cfg_exe and game_id and cfg_exe == detected_exe_name:
            return game_id, detected_exe_name, detected_exe_name
    return None, None, detected_exe_name


class RuntimeState:
    def __init__(self):
        self._lock = threading.Lock()
        self._focused_game_id = None
        self._focused_exe_name = None
        self._detected_foreground_exe = None
        self._overlay_enabled = False

    def set_focus(self, game_id, exe_name, detected_foreground_exe):
        with self._lock:
            self._focused_game_id = game_id
            self._focused_exe_name = exe_name
            self._detected_foreground_exe = detected_foreground_exe

    def get_focus(self):
        with self._lock:
            return self._focused_game_id, self._focused_exe_name, self._detected_foreground_exe

    def toggle_overlay(self):
        with self._lock:
            self._overlay_enabled = not self._overlay_enabled
            return self._overlay_enabled

    def overlay_enabled(self):
        with self._lock:
            return self._overlay_enabled


class OverlayManager:
    def __init__(self, runtime_state, stop_event, agent_token):
        self.runtime_state = runtime_state
        self.stop_event = stop_event
        self.agent_token = agent_token
        self.root = None
        self.title_var = None
        self.status_var = None
        self.notes_view = None
        self.input_text = None
        self.add_button = None
        self.visible = False
        self.current_game_id = None
        self.current_exe_name = None
        self.current_detected_exe = None
        self.notes = []
        self.events = queue.Queue()
        self.thread = None
        self._last_overlay_state = None

    def start(self):
        if os.name != "nt":
            log_event("Overlay disabled: supported only on Windows.")
            return
        self.thread = threading.Thread(target=self._run_ui, daemon=True)
        self.thread.start()

    def _run_ui(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
        except Exception as e:
            log_event(f"Overlay init failed: {e}")
            return

        self.root.title("GameTracker Overlay")
        self.root.geometry("420x280+40+40")
        self.root.attributes("-topmost", True)
        self.root.withdraw()

        container = tk.Frame(self.root, bg="#111827", padx=12, pady=10)
        container.pack(fill="both", expand=True)

        self.title_var = tk.StringVar(value="GameTracker")
        title_label = tk.Label(
            container,
            textvariable=self.title_var,
            bg="#111827",
            fg="#f9fafb",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        title_label.pack(fill="x")

        self.status_var = tk.StringVar(value="Press Ctrl+Shift+O to open overlay")
        status_label = tk.Label(
            container,
            textvariable=self.status_var,
            bg="#111827",
            fg="#9ca3af",
            font=("Segoe UI", 9),
            anchor="w",
        )
        status_label.pack(fill="x", pady=(2, 8))

        self.notes_view = tk.Text(
            container,
            bg="#1f2937",
            fg="#f9fafb",
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=10,
        )
        self.notes_view.pack(fill="both", expand=True)

        composer = tk.Frame(container, bg="#111827")
        composer.pack(fill="x", pady=(8, 0))

        self.input_text = tk.Text(
            composer,
            bg="#0f172a",
            fg="#f9fafb",
            insertbackground="#f9fafb",
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
            height=4,
        )
        self.input_text.pack(side="left", fill="x", expand=True)

        self.add_button = tk.Button(
            composer,
            text="Add note",
            command=self._create_note_from_input,
            bg="#10b981",
            fg="#0b1020",
            relief="flat",
            padx=12,
        )
        self.add_button.pack(side="left", padx=(8, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._hide)
        self.root.after(200, self._tick)
        self.root.mainloop()

    def _show(self):
        if self.root and not self.visible:
            self.root.deiconify()
            self.visible = True

    def _hide(self):
        if self.root and self.visible:
            self.root.withdraw()
            self.visible = False

    def _set_notes_text(self, value):
        if self.notes_view is None:
            return
        self.notes_view.configure(state="normal")
        self.notes_view.delete("1.0", "end")
        if value:
            self.notes_view.insert("1.0", value)
        self.notes_view.configure(state="disabled")

    def _render_notes(self):
        if not self.notes:
            self._set_notes_text("No notes yet. Add your first note below.")
            return

        lines = []
        for note in self.notes:
            created_at = note.get("created_at", "")
            created_at_fmt = created_at.replace("T", " ")[:19] if created_at else ""
            text = (note.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"[{created_at_fmt}]")
            lines.append(text)
            lines.append("")

        self._set_notes_text("\n".join(lines).strip() or "No notes yet. Add your first note below.")

    def _load_notes_async(self, game_id):
        def worker():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/agent/games/{game_id}/notes",
                    headers=get_agent_headers(self.agent_token),
                    timeout=5,
                )
                resp.raise_for_status()
                self.events.put(("notes_loaded", game_id, resp.json()))
            except Exception as e:
                self.events.put(("notes_error", game_id, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _create_note_from_input(self):
        if self.current_game_id is None or self.input_text is None:
            return
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            return
        if self.add_button:
            self.add_button.configure(state="disabled")
        self.status_var.set("Creating note...")

        def worker():
            try:
                resp = requests.post(
                    f"{SERVER_URL}/api/agent/games/{self.current_game_id}/notes",
                    json={"text": text},
                    headers=get_agent_headers(self.agent_token),
                    timeout=5,
                )
                resp.raise_for_status()
                self.events.put(("note_created", self.current_game_id))
            except Exception as e:
                self.events.put(("note_create_error", self.current_game_id, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _switch_game(self, game_id, exe_name, detected_exe_name):
        self.current_game_id = game_id
        self.current_exe_name = exe_name
        self.current_detected_exe = detected_exe_name
        log_event(
            f"Overlay focus switched: game_id={game_id}, matched_exe={exe_name}, "
            f"detected_exe={detected_exe_name}"
        )
        if game_id is None:
            self.title_var.set("GameTracker")
            if detected_exe_name:
                self.status_var.set(f"No tracked game in focus (detected: {detected_exe_name})")
            else:
                self.status_var.set("No focused process detected")
            self.notes = []
            self._render_notes()
            if self.input_text:
                self.input_text.delete("1.0", "end")
            return

        self.title_var.set(f"{exe_name or 'game'} · notes")
        self.notes = []
        self._render_notes()
        self.status_var.set("Loading notes...")
        self._load_notes_async(game_id)

    def _drain_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            event_type = event[0]
            if event_type == "notes_loaded":
                _, game_id, notes = event
                if self.current_game_id == game_id:
                    self.notes = notes
                    self._render_notes()
                    self.status_var.set("Synced")
                if self.add_button:
                    self.add_button.configure(state="normal")
            elif event_type == "notes_error":
                _, game_id, err = event
                if self.current_game_id == game_id:
                    self.status_var.set(f"Offline: {err}")
                if self.add_button:
                    self.add_button.configure(state="normal")
            elif event_type == "note_created":
                _, game_id = event
                if self.current_game_id == game_id:
                    if self.input_text:
                        self.input_text.delete("1.0", "end")
                    self.status_var.set("Note added")
                    self._load_notes_async(game_id)
                if self.add_button:
                    self.add_button.configure(state="normal")
            elif event_type == "note_create_error":
                _, game_id, err = event
                if self.current_game_id == game_id:
                    self.status_var.set(f"Create failed: {err}")
                if self.add_button:
                    self.add_button.configure(state="normal")

    def _tick(self):
        try:
            if self.stop_event.is_set():
                if self.root:
                    self.root.destroy()
                return

            self._drain_events()
            focused_game_id, focused_exe_name, detected_exe_name = self.runtime_state.get_focus()
            should_show = self.runtime_state.overlay_enabled() and (
                focused_game_id is not None or OVERLAY_SHOW_WHEN_NO_MATCH
            )
            overlay_state = (
                self.runtime_state.overlay_enabled(),
                focused_game_id,
                focused_exe_name,
                detected_exe_name,
                should_show,
            )
            if overlay_state != self._last_overlay_state:
                log_event(
                    f"Overlay state: enabled={overlay_state[0]}, "
                    f"focused_game_id={overlay_state[1]}, focused_exe={overlay_state[2]}, "
                    f"detected_exe={overlay_state[3]}, visible={overlay_state[4]}"
                )
                self._last_overlay_state = overlay_state
            if should_show:
                self._show()
            else:
                self._hide()

            if (
                focused_game_id != self.current_game_id
                or focused_exe_name != self.current_exe_name
                or detected_exe_name != self.current_detected_exe
            ):
                self._switch_game(focused_game_id, focused_exe_name, detected_exe_name)
        except Exception as e:
            log_event(f"Overlay tick error: {e}")
        finally:
            if self.root:
                self.root.after(200, self._tick)


def run_hotkey_listener(runtime_state, stop_event):
    if os.name != "nt":
        return

    user32 = ctypes.windll.user32
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    VK_SHIFT = 0x10
    VK_O = 0x4F
    WM_HOTKEY = 0x0312
    PM_REMOVE = 0x0001
    HOTKEY_ID = 1
    registered = False
    last_toggle_ts = 0.0
    poll_pressed = False
    poll_fallback_logged = False

    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_O):
        kernel32 = ctypes.windll.kernel32
        err = kernel32.GetLastError()
        log_event(f"Warning: failed to register hotkey Ctrl+Shift+O (GetLastError={err})")
    else:
        registered = True
        log_event("Hotkey registered: Ctrl+Shift+O")

    try:
        msg = wintypes.MSG()
        while not stop_event.is_set():
            # Keep processing global hotkey messages while allowing periodic stop checks.
            while registered and user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    now_ts = time.time()
                    if now_ts - last_toggle_ts < 0.25:
                        continue
                    last_toggle_ts = now_ts
                    enabled = runtime_state.toggle_overlay()
                    focused_game_id, focused_exe_name, detected_exe_name = runtime_state.get_focus()
                    log_event(
                        f"Hotkey pressed (RegisterHotKey): Ctrl+Shift+O -> "
                        f"overlay={'enabled' if enabled else 'disabled'}, "
                        f"focused_game_id={focused_game_id}, focused_exe={focused_exe_name}, "
                        f"detected_exe={detected_exe_name}"
                    )
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            # Fallback: direct keyboard state polling for environments where WM_HOTKEY is unreliable.
            is_down = (
                (user32.GetAsyncKeyState(0x11) & 0x8000)  # VK_CONTROL
                and (user32.GetAsyncKeyState(0x10) & 0x8000)  # VK_SHIFT
                and (user32.GetAsyncKeyState(0x4F) & 0x8000)  # VK_O
            )
            if is_down and not poll_pressed:
                now_ts = time.time()
                if now_ts - last_toggle_ts >= 0.25:
                    last_toggle_ts = now_ts
                    enabled = runtime_state.toggle_overlay()
                    focused_game_id, focused_exe_name, detected_exe_name = runtime_state.get_focus()
                    log_event(
                        f"Hotkey pressed (AsyncKeyState fallback): Ctrl+Shift+O -> "
                        f"overlay={'enabled' if enabled else 'disabled'}, "
                        f"focused_game_id={focused_game_id}, focused_exe={focused_exe_name}, "
                        f"detected_exe={detected_exe_name}"
                    )
                    if not poll_fallback_logged:
                        log_event("Hotkey fallback path is active")
                        poll_fallback_logged = True
                poll_pressed = True
            elif not is_down:
                poll_pressed = False
            time.sleep(0.05)
    finally:
        if registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            log_event("Hotkey unregistered: Ctrl+Shift+O")

def get_agent_config(agent_token):
    """Fetch tracking config from server."""
    try:
        response = requests.get(
            f"{SERVER_URL}/api/agent/config",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("items", [])
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching config: {e}")
        return None

def ping_server(game_id, exe_name, agent_token):
    """Send a ping to the server for the active game_id."""
    payload = {
        "game_id": game_id,
        "exe_name": exe_name,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        response = requests.post(
            f"{SERVER_URL}/api/sessions/ping",
            json=payload,
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        print(f"[{datetime.now()}] Successfully pinged for game_id={game_id}")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] Error sending ping: {e}")
        return False

def get_pending_commands(agent_token):
    try:
        response = requests.get(
            f"{SERVER_URL}/api/agent/commands",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("items", [])
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching commands: {e}")
        return []


def ack_command(game_id, request_id, success, agent_token, error=None):
    payload = {
        "game_id": game_id,
        "request_id": request_id,
        "success": success,
        "error": error,
    }
    try:
        response = requests.post(
            f"{SERVER_URL}/api/agent/commands/ack",
            json=payload,
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[{datetime.now()}] Error ack command: {e}")
        return False


def launch_game(launch_path):
    try:
        if os.name == "nt":
            os.startfile(launch_path)
        else:
            subprocess.Popen([launch_path])
        return True, None
    except Exception as e:
        return False, str(e)


def process_pending_commands(agent_token):
    commands = get_pending_commands(agent_token)
    for command in commands:
        game_id = command.get("game_id")
        request_id = command.get("request_id")
        launch_path = command.get("launch_path")

        if not game_id or not request_id or not launch_path:
            continue

        success, error = launch_game(launch_path)
        if success:
            print(f"[{datetime.now()}] Launch command executed for game_id={game_id}")
        else:
            print(f"[{datetime.now()}] Launch command failed for game_id={game_id}: {error}")
        ack_command(game_id, request_id, success, agent_token, error=error)


def check_processes(active_config, agent_token):
    """Check running processes and ping server for active games."""
    if not active_config:
        return
    
    target_exes = {}
    for item in active_config:
        exe_name = (item.get("exe_name") or "").strip().lower()
        game_id = item.get("game_id")
        if not exe_name or not game_id:
            continue
        if exe_name not in target_exes:
            target_exes[exe_name] = set()
        target_exes[exe_name].add(game_id)

    active_games_found = set()
    
    for proc in psutil.process_iter(['name']):
        try:
            p_name = proc.info.get('name')
            if p_name and p_name.lower() in target_exes:
                for game_id in target_exes[p_name.lower()]:
                    active_games_found.add((game_id, p_name))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    for game_id, exe_name in active_games_found:
        ping_server(game_id, exe_name, agent_token)
    
    return len(active_games_found)

def run_agent(stop_event, runtime_state, agent_token):
    """Main agent loop."""
    log_event("Starting GameTracker Agent...")
    
    active_config = []
    last_config_check = 0
    last_process_check = 0
    last_command_check = 0
    last_focus_check = 0
    last_focus_signature = (None, None, None)
    
    while not stop_event.is_set():
        current_time = time.time()
        
        # Update config if needed
        config_check_interval = CONFIG_POLL_INTERVAL_SECONDS if active_config else CONFIG_RETRY_INTERVAL_SECONDS
        if current_time - last_config_check > config_check_interval:
            new_config = get_agent_config(agent_token)
            if new_config is not None:
                active_config = new_config
                log_event(f"Config updated. Tracking {len(active_config)} executables.")
                if active_config:
                    log_event(
                        "Tracked executables: "
                        + ", ".join(
                            f"{(item.get('exe_name') or '').strip().lower()}(game_id={item.get('game_id')})"
                            for item in active_config
                        )
                    )
            last_config_check = current_time
        
        # Check processes (for session pings)
        if current_time - last_process_check > PING_INTERVAL_SECONDS and active_config:
            active_count = check_processes(active_config, agent_token)
            if active_count > 0:
                log_event(f"Found {active_count} active game(s)")
            last_process_check = current_time

        # Detect foreground focused game for overlay
        if current_time - last_focus_check > FOCUS_POLL_INTERVAL_SECONDS:
            focused_game_id, focused_exe_name, detected_exe_name = get_focused_game(active_config)
            runtime_state.set_focus(focused_game_id, focused_exe_name, detected_exe_name)
            current_signature = (focused_game_id, focused_exe_name, detected_exe_name)
            if current_signature != last_focus_signature:
                log_event(
                    f"Foreground check: detected_exe={detected_exe_name}, "
                    f"matched_game_id={focused_game_id}, matched_exe={focused_exe_name}"
                )
                last_focus_signature = current_signature
            last_focus_check = current_time

        # Process remote launch commands
        if current_time - last_command_check > COMMAND_POLL_INTERVAL_SECONDS:
            process_pending_commands(agent_token)
            last_command_check = current_time
        
        time.sleep(1)
    
    log_event("Agent stopped.")

def create_icon():
    """Create a simple icon for the tray."""
    from PIL import Image, ImageDraw
    
    # Create a 64x64 image
    img = Image.new('RGB', (64, 64), color='#10b981')
    draw = ImageDraw.Draw(img)
    
    # Draw a simple game controller shape
    draw.rectangle([8, 20, 56, 44], fill='#059669')
    draw.rectangle([16, 28, 24, 36], fill='#34d399')
    draw.rectangle([40, 28, 48, 36], fill='#34d399')
    
    return img

def on_clicked(icon, item):
    """Handle icon click."""
    if item == 'exit':
        icon.stop()
    elif item == 'config':
        # Open settings in browser
        import webbrowser
        webbrowser.open('http://localhost:5173/#settings')

def setup_tray():
    """Setup system tray icon."""
    try:
        import pystray
        from pystray import MenuItem as Item
        
        # Create menu
        menu = pystray.Menu(
            Item('Настройки', lambda icon: on_clicked(icon, 'config')),
            Item('Выход', lambda icon: on_clicked(icon, 'exit'))
        )
        
        # Create icon
        icon_image = create_icon()
        icon = pystray.Icon("GameTrackerAgent", icon_image, "GameTracker Agent", menu)
        
        return icon
    except Exception as e:
        print(f"Warning: Could not setup tray icon: {e}")
        print("Running in console mode...")
        return None

def main():
    """Main entry point."""
    write_startup_markers()
    stop_event = threading.Event()
    runtime_state = RuntimeState()
    log_event(f"Main started. storage_dir={get_storage_dir()}")
    agent_token = ensure_agent_token()
    if not agent_token:
        log_event("Agent token is missing. Exiting.")
        return
    
    # Try to setup tray
    tray_icon = setup_tray()

    # Start overlay + hotkey workers
    overlay_manager = OverlayManager(runtime_state, stop_event, agent_token)
    overlay_manager.start()
    hotkey_thread = threading.Thread(target=run_hotkey_listener, args=(runtime_state, stop_event), daemon=True)
    hotkey_thread.start()
    
    # Start agent in background thread
    agent_thread = threading.Thread(target=run_agent, args=(stop_event, runtime_state, agent_token), daemon=True)
    agent_thread.start()
    
    if tray_icon:
        # Run with tray icon
        tray_icon.run()
    else:
        # Run in console mode
        print("Agent is running. Press Ctrl+C to exit.")
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    
    # Stop agent
    stop_event.set()
    agent_thread.join(timeout=5)
    hotkey_thread.join(timeout=2)
    
    print("GameTracker Agent exited.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        try:
            _append_log_line(f"[{datetime.now()}] FATAL: {err}")
        except Exception:
            pass
        try:
            crash_path = os.path.join(tempfile.gettempdir(), "gametracker-agent-crash.log")
            with open(crash_path, "w", encoding="utf-8") as f:
                f.write(err)
        except Exception:
            pass
        raise
