import ctypes
import json
import logging
import os
import threading
from ctypes import wintypes


APP_NAME = "GameTracker"
AGENT_SETTINGS_FILENAME = "agent_settings.json"
AGENT_TOKEN_FILENAME = "agent_auth.bin"
logger = logging.getLogger(__name__)


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
                    except json.JSONDecodeError:
                        token = decoded
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to load agent token state from %s: %s", token_path, exc)
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
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to load agent settings from %s: %s", settings_path, exc)
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
        except OSError as exc:
            logger.warning("Failed to save agent token state: %s", exc)
        try:
            with open(get_settings_path(), "w", encoding="utf-8") as f:
                json.dump({"autostart": autostart, "server_url": server_url}, f, ensure_ascii=True, indent=2)
        except OSError as exc:
            logger.warning("Failed to save agent settings: %s", exc)

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
