import time
from typing import Callable, Dict, Optional, Protocol, Tuple


class SettingsStoreLike(Protocol):
    def set_token(self, token: str) -> None: ...
    def get_token(self) -> str: ...
    def set_refresh_token(self, refresh_token: str) -> None: ...
    def get_refresh_token(self) -> str: ...
    def set_device_id(self, device_id: str) -> None: ...
    def get_device_id(self) -> str: ...
    def set_access_expires_at(self, ts: int) -> None: ...
    def get_access_expires_at(self) -> int: ...
    def set_device_name(self, name: str) -> None: ...
    def save(self) -> None: ...


def apply_agent_auth_payload(settings_store: SettingsStoreLike, payload: Dict) -> None:
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


def refresh_if_needed(
    settings_store: SettingsStoreLike,
    server_url: str,
    refresh_call: Callable[[str, str, str], Tuple[Optional[Dict], Optional[str]]],
    is_jwt_token: Callable[[str], bool],
    log: Callable[[str, str], None],
    force: bool = False,
) -> Tuple[str, Optional[str]]:
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
        log("AUTH", f"Refreshing access token for device_id={device_id}")
        payload, err = refresh_call(server_url, device_id, refresh_token)
        if err:
            return token, err
        apply_agent_auth_payload(settings_store, payload or {})
        token = settings_store.get_token().strip()
    return token, None
