import ctypes
import json
import logging
import os
import tempfile
import threading
from ctypes import wintypes
from typing import Any


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


def _coerce_str_field(payload: dict[str, Any], key: str, *, log_scope: str) -> str:
    raw = payload.get(key)
    if raw is None:
        return ""
    if not isinstance(raw, str):
        logger.warning("%s field '%s' has invalid type %s; using default", log_scope, key, type(raw).__name__)
        return ""
    return raw.strip()


def _coerce_int_field(payload: dict[str, Any], key: str, *, log_scope: str) -> int:
    raw = payload.get(key)
    if raw in (None, ""):
        return 0
    if isinstance(raw, bool):
        logger.warning("%s field '%s' has invalid type bool; using default", log_scope, key)
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return 0
        try:
            return int(raw)
        except ValueError:
            logger.warning("%s field '%s' has invalid value %r; using default", log_scope, key, raw)
            return 0
    logger.warning("%s field '%s' has invalid type %s; using default", log_scope, key, type(raw).__name__)
    return 0


def _coerce_bool_field(payload: dict[str, Any], key: str, *, log_scope: str) -> bool:
    raw = payload.get(key)
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    logger.warning("%s field '%s' has invalid type %s; using default", log_scope, key, type(raw).__name__)
    return False


def _load_json_payload(path: str, *, binary: bool = False) -> Any:
    if binary:
        with open(path, "rb") as f:
            return json.loads(decrypt_for_current_user(f.read()).decode("utf-8").strip())
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_bytes(path: str, data: bytes) -> None:
    directory = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _atomic_write_text(path: str, data: str) -> None:
    _atomic_write_bytes(path, data.encode("utf-8"))


def _looks_like_legacy_token(raw: str) -> bool:
    token = (raw or "").strip()
    return token.count(".") == 2 and len(token) >= 16


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
                payload = _load_json_payload(token_path, binary=True)
                if isinstance(payload, dict):
                    token = _coerce_str_field(payload, "token", log_scope="Agent token state")
                    refresh_token = _coerce_str_field(payload, "refresh_token", log_scope="Agent token state")
                    device_id = _coerce_str_field(payload, "device_id", log_scope="Agent token state")
                    access_expires_at = _coerce_int_field(payload, "access_expires_at", log_scope="Agent token state")
                    device_name = _coerce_str_field(payload, "device_name", log_scope="Agent token state")
                elif isinstance(payload, str):
                    token = payload.strip()
                else:
                    logger.warning(
                        "Agent token state in %s has invalid root type %s; using defaults",
                        token_path,
                        type(payload).__name__,
                    )
            except json.JSONDecodeError:
                try:
                    with open(token_path, "rb") as f:
                        decoded = decrypt_for_current_user(f.read()).decode("utf-8").strip()
                        if _looks_like_legacy_token(decoded):
                            token = decoded
                        else:
                            logger.warning(
                                "Failed to parse agent token state from %s: invalid JSON payload",
                                token_path,
                            )
                            token = ""
                except (OSError, UnicodeDecodeError) as exc:
                    logger.warning("Failed to load agent token state from %s: %s", token_path, exc)
                    token = ""
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                logger.warning("Failed to load agent token state from %s: %s", token_path, exc)
                token = ""
        autostart = False
        server_url = ""
        settings_path = get_settings_path()
        if os.path.exists(settings_path):
            try:
                payload = _load_json_payload(settings_path)
                if not isinstance(payload, dict):
                    raise ValueError(f"invalid root type {type(payload).__name__}")
                autostart = _coerce_bool_field(payload, "autostart", log_scope="Agent settings")
                server_url = _coerce_str_field(payload, "server_url", log_scope="Agent settings").rstrip("/")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
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
            _atomic_write_bytes(get_token_path(), encrypt_for_current_user(token_payload.encode("utf-8")))
        except OSError as exc:
            logger.warning("Failed to save agent token state: %s", exc)
        try:
            settings_payload = json.dumps(
                {"autostart": autostart, "server_url": server_url},
                ensure_ascii=True,
                indent=2,
            )
            _atomic_write_text(get_settings_path(), settings_payload)
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
