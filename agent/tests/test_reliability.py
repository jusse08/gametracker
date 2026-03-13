import logging
import threading
import time
from pathlib import Path

import pytest

import auth_flow
import storage
import workers
from storage import SettingsStore


@pytest.fixture()
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage_dir = tmp_path / "agent-state"
    monkeypatch.setattr(storage, "get_storage_dir", lambda: str(storage_dir))
    monkeypatch.setattr(storage, "get_settings_path", lambda: str(storage_dir / storage.AGENT_SETTINGS_FILENAME))
    monkeypatch.setattr(storage, "get_token_path", lambda: str(storage_dir / storage.AGENT_TOKEN_FILENAME))
    return storage_dir


def test_pairing_payload_persists_server_url_for_restart_ready(isolated_storage: Path) -> None:
    store = SettingsStore()
    payload = {
        "access_token": "header.payload.signature",
        "refresh_token": "refresh-token",
        "device_id": "gt-test-device-000001",
        "device_name": "Living Room PC",
        "access_expires_in": 300,
    }

    auth_flow.apply_agent_pairing_payload(store, "http://192.168.1.50:8000/", payload)

    restarted = SettingsStore()
    restarted.load()

    assert restarted.get_server_url() == "http://192.168.1.50:8000"
    assert restarted.get_token() == payload["access_token"]
    assert restarted.get_refresh_token() == payload["refresh_token"]
    assert restarted.get_device_id() == payload["device_id"]
    assert restarted.get_device_name() == payload["device_name"]
    assert restarted.get_access_expires_at() > int(time.time())


def test_settings_store_load_recovers_from_invalid_json(
    isolated_storage: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token_path = isolated_storage / storage.AGENT_TOKEN_FILENAME
    settings_path = isolated_storage / storage.AGENT_SETTINGS_FILENAME
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_bytes(storage.encrypt_for_current_user(b"\xff"))
    settings_path.write_text("{broken", encoding="utf-8")

    caplog.set_level(logging.WARNING)
    store = SettingsStore()
    store.load()

    assert store.get_token() == ""
    assert store.get_refresh_token() == ""
    assert store.get_device_id() == ""
    assert store.get_access_expires_at() == 0
    assert store.get_device_name() == ""
    assert store.get_server_url() == ""
    assert store.get_autostart() is False
    assert "Failed to load agent token state" in caplog.text
    assert "Failed to load agent settings" in caplog.text


def test_settings_store_load_recovers_from_invalid_field_types(
    isolated_storage: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token_path = isolated_storage / storage.AGENT_TOKEN_FILENAME
    settings_path = isolated_storage / storage.AGENT_SETTINGS_FILENAME
    token_payload = (
        '{"token":["bad"],"refresh_token":" refresh ","device_id":123,'
        '"access_expires_at":"not-a-number","device_name":{"nested":true}}'
    )
    settings_payload = '{"autostart":"yes","server_url":["http://server:8000"]}'

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_bytes(storage.encrypt_for_current_user(token_payload.encode("utf-8")))
    settings_path.write_text(settings_payload, encoding="utf-8")

    caplog.set_level(logging.WARNING)
    store = SettingsStore()
    store.load()

    assert store.get_token() == ""
    assert store.get_refresh_token() == "refresh"
    assert store.get_device_id() == ""
    assert store.get_access_expires_at() == 0
    assert store.get_device_name() == ""
    assert store.get_server_url() == ""
    assert store.get_autostart() is False
    assert "Agent token state field 'token' has invalid type list" in caplog.text
    assert "Agent token state field 'device_id' has invalid type int" in caplog.text
    assert "Agent token state field 'access_expires_at' has invalid value 'not-a-number'" in caplog.text
    assert "Agent settings field 'autostart' has invalid type str" in caplog.text
    assert "Agent settings field 'server_url' has invalid type list" in caplog.text


class FakeSettingsStore:
    def __init__(
        self,
        *,
        token: str = "",
        refresh_token: str = "",
        device_id: str = "",
        access_expires_at: int = 0,
        server_url: str = "",
    ) -> None:
        self.token = token
        self.refresh_token = refresh_token
        self.device_id = device_id
        self.access_expires_at = access_expires_at
        self.server_url = server_url
        self.device_name = ""
        self.saved = 0

    def set_token(self, token: str) -> None:
        self.token = token

    def get_token(self) -> str:
        return self.token

    def set_refresh_token(self, refresh_token: str) -> None:
        self.refresh_token = refresh_token

    def get_refresh_token(self) -> str:
        return self.refresh_token

    def set_device_id(self, device_id: str) -> None:
        self.device_id = device_id

    def get_device_id(self) -> str:
        return self.device_id

    def set_access_expires_at(self, ts: int) -> None:
        self.access_expires_at = ts

    def get_access_expires_at(self) -> int:
        return self.access_expires_at

    def set_device_name(self, name: str) -> None:
        self.device_name = name

    def get_device_name(self) -> str:
        return self.device_name

    def set_server_url(self, server_url: str) -> None:
        self.server_url = server_url

    def get_server_url(self) -> str:
        return self.server_url

    def save(self) -> None:
        self.saved += 1


class FakeSharedState:
    def __init__(self) -> None:
        self.last_error = ""
        self.api_ok = False

    def set_last_error(self, value: str) -> None:
        self.last_error = value

    def get_last_error(self) -> str:
        return self.last_error

    def mark_api_ok(self, value: bool) -> None:
        self.api_ok = bool(value)

    def set_config_items(self, _items) -> None:
        pass

    def get_config_items(self):
        return []

    def is_ws_connected(self) -> bool:
        return False

    def mark_ping(self, _pinged: int) -> None:
        pass

    def mark_command_poll(self) -> None:
        pass

    def mark_command_exec(self) -> None:
        pass


def test_refresh_if_needed_keeps_state_when_refresh_is_denied() -> None:
    store = FakeSettingsStore(
        token="header.payload.signature",
        refresh_token="refresh-token",
        device_id="gt-test-device-000001",
        access_expires_at=0,
    )
    calls: list[tuple[str, str, str]] = []

    def refresh_call(server_url: str, device_id: str, refresh_token: str):
        calls.append((server_url, device_id, refresh_token))
        return None, "401 Invalid refresh token"

    token, err = auth_flow.refresh_if_needed(
        settings_store=store,
        server_url="http://server:8000",
        refresh_call=refresh_call,
        is_jwt_token=lambda value: value.count(".") == 2,
        log=lambda *_args: None,
        force=True,
    )

    assert token == "header.payload.signature"
    assert err == "401 Invalid refresh token"
    assert calls == [("http://server:8000", "gt-test-device-000001", "refresh-token")]
    assert store.refresh_token == "refresh-token"
    assert store.saved == 0


def test_agent_worker_does_not_mask_typeerror_from_command_processor() -> None:
    stop_event = threading.Event()
    reconnect_event = threading.Event()
    manual_refresh_event = threading.Event()
    manual_refresh_event.set()
    command_refresh_event = threading.Event()
    settings_store = FakeSettingsStore(server_url="http://server:8000")
    shared_state = FakeSharedState()

    with pytest.raises(TypeError, match="processor boom"):
        workers.agent_worker(
            stop_event=stop_event,
            reconnect_event=reconnect_event,
            manual_refresh_event=manual_refresh_event,
            command_refresh_event=command_refresh_event,
            settings_store=settings_store,
            shared_state=shared_state,
            validate_server_url_fn=lambda url: (url, None),
            refresh_if_needed_fn=lambda _store, _url: ("header.payload.signature", None),
            validate_agent_token_fn=lambda token: (token, None),
            get_agent_config_fn=lambda _url, _token: [],
            run_command_processor_fn=lambda _url, _token, _handled_requests: (_ for _ in ()).throw(TypeError("processor boom")),
            check_processes_and_ping_fn=lambda _url, _items, _token, _watcher: (0, 0),
            process_watcher=object(),
            debug_log_fn=lambda *_args: None,
            config_fallback_poll_seconds=5,
            ping_interval_seconds=10,
            command_poll_interval_seconds=6,
            command_watchdog_interval_seconds=90,
        )
