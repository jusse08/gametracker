import json
import random
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

HandledRequests = Dict[str, Tuple[float, bool]]


def _websocket_error_types(websocket_module) -> Tuple[type[BaseException], ...]:
    candidates = [
        OSError,
        getattr(websocket_module, "WebSocketException", None),
        getattr(websocket_module, "WebSocketConnectionClosedException", None),
    ]
    return tuple(
        candidate
        for candidate in candidates
        if isinstance(candidate, type) and issubclass(candidate, BaseException)
    )


def run_command_processor(
    server_url: str,
    agent_token: str,
    get_pending_commands_fn: Callable[[str, str], List[Dict]],
    launch_game_fn: Callable[[str], Tuple[bool, Optional[str]]],
    ack_command_fn: Callable[[str, int, str, bool, str, Optional[str]], None],
    debug_log_fn: Callable[[str, str], None],
    handled_requests: Optional[HandledRequests] = None,
    dedupe_ttl_seconds: int = 600,
) -> Tuple[int, int]:
    commands = get_pending_commands_fn(server_url, agent_token)
    total = len(commands)
    success_count = 0
    now = time.time()
    if handled_requests is not None and dedupe_ttl_seconds > 0:
        expire_before = now - dedupe_ttl_seconds
        stale = [req_id for req_id, (ts, _ok) in handled_requests.items() if ts < expire_before]
        for req_id in stale:
            handled_requests.pop(req_id, None)
    if commands:
        debug_log_fn("CMD", f"Processing {len(commands)} pending command(s)")
    for command in commands:
        game_id = command.get("game_id")
        request_id = command.get("request_id")
        launch_path = (command.get("launch_path") or "").strip()
        if not game_id or not request_id or not launch_path:
            debug_log_fn("CMD", "Skipped command with missing fields")
            continue
        if handled_requests is not None:
            prev = handled_requests.get(request_id)
            if prev and prev[1]:
                debug_log_fn("CMD", f"Skipping duplicate command req={request_id}: already executed successfully")
                ack_command_fn(server_url, game_id, request_id, True, agent_token, None)
                continue
        debug_log_fn("CMD", f"Launch command game_id={game_id} req={request_id}")
        success, error = launch_game_fn(launch_path)
        if success:
            success_count += 1
        if handled_requests is not None:
            handled_requests[request_id] = (now, bool(success))
        ack_command_fn(server_url, game_id, request_id, success, agent_token, error)
    return total, success_count


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


def check_processes_and_ping(
    server_url: str,
    config_items: List[Dict],
    agent_token: str,
    ping_server_fn: Callable[[str, int, str, str], bool],
    watcher: object,
    debug_log_fn: Callable[[str, str], None],
) -> Tuple[int, int]:
    targets = build_unique_exe_targets(config_items)
    if not targets:
        debug_log_fn("PING", "No unique exe targets to watch")
        return 0, 0

    running_exes = watcher.get_running_targets(set(targets.keys()))

    pinged = 0
    for exe_name, game_id in targets.items():
        if exe_name in running_exes and ping_server_fn(server_url, game_id, exe_name, agent_token):
            pinged += 1
    debug_log_fn("PING", f"Process check: targets={len(targets)} active_targets={len(running_exes)} pinged={pinged}")
    return pinged, len(targets)


def ws_worker(
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    command_refresh_event: threading.Event,
    settings_store,
    shared_state,
    *,
    websocket_module,
    validate_server_url_fn: Callable[[str], Tuple[str, Optional[str]]],
    refresh_if_needed_fn: Callable[[object, str], Tuple[str, Optional[str]]],
    validate_agent_token_fn: Callable[[str], Tuple[str, Optional[str]]],
    build_ws_url_fn: Callable[[str, str], str],
    build_ws_log_url_fn: Callable[[str], str],
    debug_log_fn: Callable[[str, str], None],
    ws_reconnect_delay_seconds: int,
    ws_reconnect_max_delay_seconds: int,
) -> None:
    debug_log_fn("WS", "WS worker started")
    reconnect_delay = ws_reconnect_delay_seconds
    websocket_errors = _websocket_error_types(websocket_module)
    while not stop_event.is_set():
        server_url = settings_store.get_server_url()
        valid_server_url, server_url_error = validate_server_url_fn(server_url)
        if server_url_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(server_url_error)
            shared_state.mark_api_ok(False)
            debug_log_fn("WS", f"Invalid server URL: {server_url_error}")
            time.sleep(1)
            continue
        valid_token, refresh_error = refresh_if_needed_fn(settings_store, valid_server_url)
        if refresh_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(f"Token refresh failed: {refresh_error}")
            shared_state.mark_api_ok(False)
            debug_log_fn("WS", f"Token refresh failed: {refresh_error}")
            time.sleep(2)
            continue
        valid_token, token_error = validate_agent_token_fn(valid_token)
        if token_error:
            shared_state.set_ws_connected(False)
            shared_state.set_last_error(token_error)
            shared_state.mark_api_ok(False)
            debug_log_fn("WS", f"Invalid token: {token_error}")
            time.sleep(1)
            continue

        ws = None
        force_reconnect_now = False
        shared_state.set_last_error("")
        try:
            ws_url = build_ws_url_fn(valid_server_url, valid_token)
            debug_log_fn("WS", f"Connecting to {build_ws_log_url_fn(valid_server_url)}")
            ws = websocket_module.create_connection(ws_url, timeout=5)
            ws.settimeout(1)
            shared_state.set_ws_connected(True)
            shared_state.mark_api_ok(True)
            debug_log_fn("WS", "Connected")
            reconnect_delay = ws_reconnect_delay_seconds
            next_keepalive = time.time() + 15

            while not stop_event.is_set():
                if reconnect_event.is_set():
                    force_reconnect_now = True
                    debug_log_fn("WS", "Reconnect signal received: restarting WebSocket session")
                    break

                if time.time() >= next_keepalive:
                    try:
                        ws.send("ping")
                    except websocket_errors:
                        break
                    next_keepalive = time.time() + 15

                try:
                    raw = ws.recv()
                except websocket_module.WebSocketTimeoutException:
                    continue
                except websocket_errors:
                    break

                if not raw:
                    continue

                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = payload.get("type")
                if msg_type == "config_snapshot":
                    items = payload.get("items") or []
                    shared_state.set_config_items(items)
                    debug_log_fn("WS", f"config_snapshot received: {len(items)} item(s)")
                elif msg_type == "commands_updated":
                    command_refresh_event.set()
                    debug_log_fn("WS", "commands_updated received")

        except websocket_errors as e:
            shared_state.set_last_error(str(e))
            debug_log_fn("WS", f"Disconnected: {e}")
        finally:
            shared_state.set_ws_connected(False)
            if ws:
                try:
                    ws.close()
                except websocket_errors:
                    pass
            debug_log_fn("WS", "Connection closed")

        if not stop_event.is_set():
            if force_reconnect_now:
                reconnect_event.clear()
                debug_log_fn("WS", "Reconnect requested: reconnecting immediately")
                continue
            if reconnect_event.is_set():
                reconnect_event.clear()
                debug_log_fn("WS", "Reconnect requested: reconnecting immediately")
                continue
            jitter = random.uniform(0.8, 1.25)
            sleep_for = max(1.0, reconnect_delay * jitter)
            time.sleep(sleep_for)
            debug_log_fn("WS", f"Reconnect in {sleep_for:.1f}s")
            reconnect_delay = min(ws_reconnect_max_delay_seconds, reconnect_delay * 2)


def agent_worker(
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    manual_refresh_event: threading.Event,
    command_refresh_event: threading.Event,
    settings_store,
    shared_state,
    *,
    validate_server_url_fn: Callable[[str], Tuple[str, Optional[str]]],
    refresh_if_needed_fn: Callable[[object, str], Tuple[str, Optional[str]]],
    validate_agent_token_fn: Callable[[str], Tuple[str, Optional[str]]],
    get_agent_config_fn: Callable[[str, str], Optional[List[Dict]]],
    run_command_processor_fn: Callable[[str, str, Optional[HandledRequests]], Tuple[int, int]],
    check_processes_and_ping_fn: Callable[[str, List[Dict], str, object], Tuple[int, int]],
    process_watcher: object,
    debug_log_fn: Callable[[str, str], None],
    config_fallback_poll_seconds: int,
    ping_interval_seconds: int,
    command_poll_interval_seconds: int,
    command_watchdog_interval_seconds: int,
) -> None:
    last_config_poll = 0.0
    last_ping = 0.0
    last_command_poll = 0.0
    last_watchdog_poll = 0.0
    handled_requests: HandledRequests = {}

    def _run_processor(server_url: str, token: str) -> Tuple[int, int]:
        return run_command_processor_fn(server_url, token, handled_requests)

    debug_log_fn("AGENT", "Agent worker started")
    while not stop_event.is_set():
        server_url = settings_store.get_server_url()
        valid_server_url, server_url_error = validate_server_url_fn(server_url)
        if server_url_error:
            shared_state.set_last_error(server_url_error)
            shared_state.mark_api_ok(False)
            debug_log_fn("AGENT", f"Invalid server URL: {server_url_error}")
            time.sleep(1)
            continue
        valid_token, refresh_error = refresh_if_needed_fn(settings_store, valid_server_url)
        if refresh_error:
            shared_state.set_last_error(f"Token refresh failed: {refresh_error}")
            shared_state.mark_api_ok(False)
            debug_log_fn("AGENT", f"Token refresh failed: {refresh_error}")
            time.sleep(2)
            continue
        valid_token, token_error = validate_agent_token_fn(valid_token)
        if token_error:
            shared_state.set_last_error(token_error)
            shared_state.mark_api_ok(False)
            debug_log_fn("AGENT", f"Invalid token: {token_error}")
            time.sleep(1)
            continue

        now = time.time()
        force_manual_refresh = manual_refresh_event.is_set()
        if force_manual_refresh:
            manual_refresh_event.clear()
            debug_log_fn("AGENT", "Manual refresh requested")

        if force_manual_refresh:
            config = get_agent_config_fn(valid_server_url, valid_token)
            if config is not None:
                shared_state.set_config_items(config)
                shared_state.mark_api_ok(True)
                debug_log_fn("AGENT", f"Manual config refresh -> {len(config)} item(s)")
            else:
                shared_state.mark_api_ok(False)
            total_cmd, _ = _run_processor(valid_server_url, valid_token)
            shared_state.mark_command_poll()
            if total_cmd > 0:
                shared_state.mark_command_exec()
                shared_state.mark_api_ok(True)
            last_command_poll = now
            last_watchdog_poll = now
            last_config_poll = now
        elif (not shared_state.is_ws_connected()) and (now - last_config_poll >= config_fallback_poll_seconds):
            config = get_agent_config_fn(valid_server_url, valid_token)
            if config is not None:
                shared_state.set_config_items(config)
                shared_state.mark_api_ok(True)
                debug_log_fn("AGENT", f"Fallback config refresh -> {len(config)} item(s)")
            else:
                shared_state.mark_api_ok(False)
            last_config_poll = now

        if now - last_ping >= ping_interval_seconds:
            pinged, _targets = check_processes_and_ping_fn(
                valid_server_url,
                shared_state.get_config_items(),
                valid_token,
                process_watcher,
            )
            shared_state.mark_ping(pinged)
            last_ping = now

        force_command_poll = command_refresh_event.is_set()
        offline_poll_due = (not shared_state.is_ws_connected()) and (now - last_command_poll >= command_poll_interval_seconds)
        watchdog_due = now - last_watchdog_poll >= command_watchdog_interval_seconds
        if force_command_poll or offline_poll_due or watchdog_due:
            command_refresh_event.clear()
            total_cmd, _ = _run_processor(valid_server_url, valid_token)
            shared_state.mark_command_poll()
            if total_cmd > 0:
                shared_state.mark_command_exec()
            shared_state.mark_api_ok(True)
            last_command_poll = now
            if watchdog_due:
                last_watchdog_poll = now

        if reconnect_event.is_set():
            reconnect_event.clear()

        time.sleep(1)
