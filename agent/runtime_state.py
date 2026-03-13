import threading
import time
from typing import Dict, List

import psutil


class SharedState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config_items: List[Dict] = []
        self._ws_connected = False
        self._last_error = ""
        self._api_ok = False
        self._last_api_ok_at = 0.0
        self._last_ws_connected_at = 0.0
        self._last_config_sync_at = 0.0
        self._last_command_poll_at = 0.0
        self._last_command_exec_at = 0.0
        self._last_ping_at = 0.0
        self._last_ping_count = 0

    def set_config_items(self, items: List[Dict]) -> None:
        with self._lock:
            self._config_items = list(items or [])
            self._last_config_sync_at = time.time()

    def get_config_items(self) -> List[Dict]:
        with self._lock:
            return list(self._config_items)

    def set_ws_connected(self, value: bool) -> None:
        with self._lock:
            self._ws_connected = bool(value)
            if self._ws_connected:
                self._last_ws_connected_at = time.time()

    def is_ws_connected(self) -> bool:
        with self._lock:
            return self._ws_connected

    def set_last_error(self, value: str) -> None:
        with self._lock:
            self._last_error = value or ""

    def get_last_error(self) -> str:
        with self._lock:
            return self._last_error

    def mark_api_ok(self, value: bool) -> None:
        with self._lock:
            self._api_ok = bool(value)
            if self._api_ok:
                self._last_api_ok_at = time.time()

    def mark_command_poll(self) -> None:
        with self._lock:
            self._last_command_poll_at = time.time()

    def mark_command_exec(self) -> None:
        with self._lock:
            self._last_command_exec_at = time.time()

    def mark_ping(self, pinged: int) -> None:
        with self._lock:
            self._last_ping_at = time.time()
            self._last_ping_count = max(int(pinged), 0)

    def get_health_snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {
                "api_ok": 1.0 if self._api_ok else 0.0,
                "last_api_ok_at": self._last_api_ok_at,
                "last_ws_connected_at": self._last_ws_connected_at,
                "last_config_sync_at": self._last_config_sync_at,
                "last_command_poll_at": self._last_command_poll_at,
                "last_command_exec_at": self._last_command_exec_at,
                "last_ping_at": self._last_ping_at,
                "last_ping_count": float(self._last_ping_count),
            }


class ProcessTargetWatcher:
    def __init__(self, full_scan_interval_seconds: int = 20) -> None:
        self._cached_pids: Dict[str, set[int]] = {}
        self._last_full_scan_at = 0.0
        self._full_scan_interval_seconds = max(1, int(full_scan_interval_seconds))

    def _check_cached(self, targets: set[str]) -> set[str]:
        found: set[str] = set()
        next_cache: Dict[str, set[int]] = {}
        for exe in targets:
            candidate_pids = self._cached_pids.get(exe, set())
            alive: set[int] = set()
            for pid in candidate_pids:
                try:
                    proc = psutil.Process(pid)
                    name = (proc.name() or "").strip().lower()
                    if name == exe and proc.is_running():
                        alive.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            if alive:
                next_cache[exe] = alive
                found.add(exe)
        self._cached_pids = next_cache
        return found

    def _full_scan(self, targets: set[str]) -> set[str]:
        found: set[str] = set()
        next_cache: Dict[str, set[int]] = {exe: set() for exe in targets}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").strip().lower()
                if name in next_cache:
                    pid = int(proc.info.get("pid") or 0)
                    if pid > 0:
                        next_cache[name].add(pid)
                        found.add(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError, TypeError):
                continue
        self._cached_pids = {exe: pids for exe, pids in next_cache.items() if pids}
        self._last_full_scan_at = time.time()
        return found

    def get_running_targets(self, targets: set[str]) -> set[str]:
        if not targets:
            self._cached_pids = {}
            return set()

        found = self._check_cached(targets)
        now = time.time()
        if (now - self._last_full_scan_at) >= self._full_scan_interval_seconds:
            found = self._full_scan(targets)
        return found
