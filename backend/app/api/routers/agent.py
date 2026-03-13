import os
import ntpath
import secrets
import re
import threading
import asyncio
import hashlib
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Any, Dict, List, Optional, Set

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.auth import ALGORITHM, SECRET_KEY, create_access_token, get_current_user
from app.core.database import get_session, engine
from app.domain.models import (
    AgentConfig,
    AgentConfigRead,
    AgentDevice,
    AgentDeviceRead,
    AgentPairCode,
    Game,
    GameRead,
    Note,
    NoteCreate,
    NoteRead,
    Session as DbSession,
    User,
)
from app.domain.schemas import (
    AgentConfigRequest,
    AgentDeviceUpdateRequest,
    AgentLaunchAckRequest,
    AgentLaunchRequest,
    AgentNoteUpdateRequest,
    AgentPairRequest,
    AgentRefreshRequest,
    AgentTestPingRequest,
    PingRequest,
)
from app.services.common import (
    build_game_read,
    ensure_owned_game_with_detail,
    ensure_owned_note_with_detail,
    get_total_playtime_map,
    get_agent_config_by_game_id,
    upsert_agent_session,
)

router = APIRouter()
AGENT_HEARTBEAT_TIMEOUT_SECONDS = 30
AGENT_LIVE_HEARTBEAT_TIMEOUT_SECONDS = 20
AGENT_PAIR_CODE_TTL_SECONDS = 600
AGENT_ACCESS_TOKEN_TTL_MINUTES = 15
AGENT_REFRESH_TOKEN_TTL_DAYS = 30
AGENT_SESSION_GAP_SECONDS = 30
WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


class AgentWsManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        with self._lock:
            conns = self._connections.get(user_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(user_id, None)

    def _schedule_send(self, user_id: int, payload: Dict[str, Any]) -> None:
        if not self._loop:
            return
        future = asyncio.run_coroutine_threadsafe(self._broadcast(user_id, payload), self._loop)
        future.add_done_callback(lambda _: None)

    async def _broadcast(self, user_id: int, payload: Dict[str, Any]) -> None:
        with self._lock:
            targets = list(self._connections.get(user_id, set()))
        if not targets:
            return
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(user_id, ws)

    def notify_snapshot(self, user_id: int, items: List[Dict[str, Any]]) -> None:
        self._schedule_send(user_id, {"type": "config_snapshot", "items": items})

    def notify_commands_updated(self, user_id: int) -> None:
        self._schedule_send(user_id, {"type": "commands_updated"})

    def disconnect_all(self, user_id: int) -> None:
        if not self._loop:
            return
        with self._lock:
            targets = list(self._connections.get(user_id, set()))
        for ws in targets:
            asyncio.run_coroutine_threadsafe(ws.close(code=1008), self._loop)


WS_MANAGER = AgentWsManager()


def _hash_value(raw: str) -> str:
    payload = f"{SECRET_KEY}:{raw}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _extract_bearer_token(authorization: str) -> str:
    auth = (authorization or "").strip()
    if not auth.lower().startswith("bearer "):
        return ""
    return auth[7:].strip()


def _validate_device_id(raw: str) -> str:
    device_id = (raw or "").strip()
    if not device_id or len(device_id) < 12 or len(device_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid device_id")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", device_id):
        raise HTTPException(status_code=400, detail="Invalid device_id format")
    return device_id


def _validate_device_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=400, detail="Invalid device_name")
    return name


def _issue_agent_tokens(user_id: int, device_id: str) -> Dict[str, Any]:
    access_ttl = timedelta(minutes=AGENT_ACCESS_TOKEN_TTL_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user_id), "agent": True, "device_id": device_id},
        expires_delta=access_ttl,
    )
    refresh_token = secrets.token_urlsafe(48)
    refresh_hash = _hash_value(refresh_token)
    refresh_expires_at = datetime.utcnow() + timedelta(days=AGENT_REFRESH_TOKEN_TTL_DAYS)
    return {
        "access_token": access_token,
        "access_expires_in": int(access_ttl.total_seconds()),
        "refresh_token": refresh_token,
        "refresh_hash": refresh_hash,
        "refresh_expires_at": refresh_expires_at,
    }


def _get_agent_user_by_access_token(session: Session, token: str) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid access token")

    if payload.get("agent") is not True:
        raise HTTPException(status_code=401, detail="Token is not agent token")

    user_id_str = payload.get("sub")
    device_id = (payload.get("device_id") or "").strip()
    if not user_id_str or not device_id:
        raise HTTPException(status_code=401, detail="Invalid access token payload")

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid access token payload")

    device = session.exec(
        select(AgentDevice).where(
            AgentDevice.device_id == device_id,
            AgentDevice.user_id == user_id,
        )
    ).first()
    if not device or device.revoked_at or device.refresh_expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Agent device is revoked or expired")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    now = datetime.utcnow()
    device.last_seen_at = now
    session.add(device)
    session.commit()
    _touch_agent_heartbeat(session, user)
    return user


def _touch_agent_heartbeat(session: Session, agent_user: User) -> None:
    now = datetime.utcnow()
    if (
        not agent_user.agent_last_seen_at
        or (now - agent_user.agent_last_seen_at).total_seconds() >= 1
    ):
        agent_user.agent_last_seen_at = now
        session.add(agent_user)
        session.commit()


def _get_agent_user_by_token(session: Session, token: str) -> User:
    raw_token = (token or "").strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing agent token")
    return _get_agent_user_by_access_token(session, raw_token)


def get_agent_user(
    *,
    session: Session = Depends(get_session),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> User:
    bearer_token = _extract_bearer_token(authorization or "")
    token = bearer_token
    return _get_agent_user_by_token(session, token)


def normalize_and_validate_launch_path(launch_path: str) -> str:
    normalized = (launch_path or "").strip().strip('"')
    if not normalized:
        raise HTTPException(status_code=400, detail="launch_path is required")
    if "\x00" in normalized:
        raise HTTPException(status_code=400, detail="launch_path contains null byte")
    if normalized.startswith("\\\\"):
        raise HTTPException(status_code=400, detail="UNC paths are not allowed")
    if normalized.startswith("http://") or normalized.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL launch paths are not allowed")
    if not WINDOWS_ABS_PATH_RE.match(normalized):
        raise HTTPException(status_code=400, detail="launch_path must be an absolute Windows path")
    normalized = normalized.replace("/", "\\")
    if not normalized.lower().endswith(".exe"):
        raise HTTPException(status_code=400, detail="launch_path must point to .exe")
    return normalized


def extract_exe_name(launch_path: str) -> str:
    exe_name = ntpath.basename(launch_path)
    if not exe_name:
        raise HTTPException(status_code=400, detail="Не удалось определить exe из launch_path")
    if not exe_name.lower().endswith(".exe"):
        raise HTTPException(status_code=400, detail="Исполняемый файл должен иметь расширение .exe")
    return exe_name


def build_agent_config_items(session: Session, user_id: int) -> List[Dict[str, Any]]:
    rows = session.exec(
        select(AgentConfig, Game)
        .join(Game, AgentConfig.game_id == Game.id)
        .where(Game.user_id == user_id)
        .order_by(Game.title.asc())
    ).all()
    items: List[Dict[str, Any]] = []
    for cfg, game in rows:
        if not cfg.exe_name:
            continue
        items.append(
            {
                "game_id": cfg.game_id,
                "title": game.title,
                "exe_name": cfg.exe_name,
                "launch_path": cfg.launch_path,
                "enabled": cfg.enabled,
                "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
            }
        )
    return items


@router.post("/api/agent/pair-code")
def create_agent_pair_code(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    active_codes = session.exec(
        select(AgentPairCode).where(
            AgentPairCode.user_id == current_user.id,
            AgentPairCode.consumed_at == None,
            AgentPairCode.expires_at > now,
        )
    ).all()
    for row in active_codes:
        session.delete(row)

    code = f"{secrets.randbelow(900000) + 100000}"
    session.add(
        AgentPairCode(
            user_id=current_user.id,
            code_hash=_hash_value(code),
            expires_at=now + timedelta(seconds=AGENT_PAIR_CODE_TTL_SECONDS),
        )
    )
    session.commit()
    return {
        "ok": True,
        "pair_code": code,
        "expires_in": AGENT_PAIR_CODE_TTL_SECONDS,
        "expires_at": (now + timedelta(seconds=AGENT_PAIR_CODE_TTL_SECONDS)).isoformat(),
    }


@router.post("/api/agent/pair")
def pair_agent_device(
    *,
    session: Session = Depends(get_session),
    req: AgentPairRequest,
):
    now = datetime.utcnow()
    pair_hash = _hash_value((req.pair_code or "").strip())
    pair_row = session.exec(
        select(AgentPairCode).where(
            AgentPairCode.code_hash == pair_hash,
            AgentPairCode.consumed_at == None,
            AgentPairCode.expires_at > now,
        )
    ).first()
    if not pair_row:
        raise HTTPException(status_code=401, detail="Invalid or expired pair code")

    device_id = _validate_device_id(req.device_id)
    device_name = _validate_device_name(req.device_name)
    tokens = _issue_agent_tokens(pair_row.user_id, device_id)

    device = session.exec(select(AgentDevice).where(AgentDevice.device_id == device_id)).first()
    if device and device.user_id != pair_row.user_id:
        raise HTTPException(status_code=409, detail="Device already bound to another account")

    if not device:
        device = AgentDevice(
            user_id=pair_row.user_id,
            device_id=device_id,
            device_name=device_name,
            refresh_token_hash=tokens["refresh_hash"],
            refresh_expires_at=tokens["refresh_expires_at"],
            last_seen_at=now,
        )
    else:
        device.device_name = device_name
        device.refresh_token_hash = tokens["refresh_hash"]
        device.refresh_expires_at = tokens["refresh_expires_at"]
        device.last_seen_at = now
        device.revoked_at = None

    pair_row.consumed_at = now
    session.add(device)
    session.add(pair_row)
    session.commit()

    return {
        "ok": True,
        "token_type": "bearer",
        "access_token": tokens["access_token"],
        "access_expires_in": tokens["access_expires_in"],
        "refresh_token": tokens["refresh_token"],
        "refresh_expires_at": tokens["refresh_expires_at"].isoformat(),
        "device_id": device_id,
        "device_name": device_name,
    }


@router.post("/api/agent/auth/refresh")
def refresh_agent_access_token(
    *,
    session: Session = Depends(get_session),
    req: AgentRefreshRequest,
):
    now = datetime.utcnow()
    device_id = _validate_device_id(req.device_id)
    refresh_hash = _hash_value((req.refresh_token or "").strip())
    device = session.exec(
        select(AgentDevice).where(
            AgentDevice.device_id == device_id,
            AgentDevice.refresh_token_hash == refresh_hash,
        )
    ).first()
    if not device or device.revoked_at or device.refresh_expires_at < now:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    tokens = _issue_agent_tokens(device.user_id, device.device_id)
    device.refresh_token_hash = tokens["refresh_hash"]
    device.refresh_expires_at = tokens["refresh_expires_at"]
    device.last_seen_at = now
    session.add(device)
    session.commit()

    user = session.get(User, device.user_id)
    if user:
        _touch_agent_heartbeat(session, user)

    return {
        "ok": True,
        "token_type": "bearer",
        "access_token": tokens["access_token"],
        "access_expires_in": tokens["access_expires_in"],
        "refresh_token": tokens["refresh_token"],
        "refresh_expires_at": tokens["refresh_expires_at"].isoformat(),
        "device_id": device.device_id,
        "device_name": device.device_name,
    }


@router.put("/api/agent/device/self")
def update_current_agent_device(
    *,
    session: Session = Depends(get_session),
    req: AgentDeviceUpdateRequest,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    token = _extract_bearer_token(authorization or "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid access token")

    if payload.get("agent") is not True:
        raise HTTPException(status_code=401, detail="Token is not agent token")

    user_id_str = payload.get("sub")
    device_id = (payload.get("device_id") or "").strip()
    if not user_id_str or not device_id:
        raise HTTPException(status_code=401, detail="Invalid access token payload")
    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid access token payload")

    device = session.exec(
        select(AgentDevice).where(
            AgentDevice.user_id == user_id,
            AgentDevice.device_id == device_id,
        )
    ).first()
    if not device or device.revoked_at or device.refresh_expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Agent device is revoked or expired")

    device.device_name = _validate_device_name(req.device_name)
    device.last_seen_at = datetime.utcnow()
    session.add(device)
    session.commit()

    return {"ok": True, "device_id": device.device_id, "device_name": device.device_name}


@router.get("/api/agent/devices", response_model=List[AgentDeviceRead])
def list_agent_devices(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = session.exec(
        select(AgentDevice)
        .where(AgentDevice.user_id == current_user.id)
        .order_by(AgentDevice.created_at.desc())
    ).all()
    return rows


@router.post("/api/agent/devices/{device_id}/revoke")
def revoke_agent_device(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    device_id: str,
):
    normalized = _validate_device_id(device_id)
    row = session.exec(
        select(AgentDevice).where(
            AgentDevice.user_id == current_user.id,
            AgentDevice.device_id == normalized,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    row.revoked_at = datetime.utcnow()
    session.add(row)
    session.commit()
    WS_MANAGER.disconnect_all(current_user.id)
    return {"ok": True}


@router.get("/api/agent/config")
def get_agent_config(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
):
    items = [item for item in build_agent_config_items(session, agent_user.id) if item["enabled"]]
    return {"items": items}


@router.websocket("/api/agent/ws")
async def agent_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    with Session(engine) as session:
        try:
            user = _get_agent_user_by_token(session, token)
        except HTTPException as exc:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=exc.detail)

        WS_MANAGER.bind_loop(asyncio.get_running_loop())
        await WS_MANAGER.connect(user.id, websocket)
        await websocket.send_json({"type": "config_snapshot", "items": build_agent_config_items(session, user.id)})

        try:
            while True:
                _ = await websocket.receive_text()
                _touch_agent_heartbeat(session, user)
                await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            WS_MANAGER.disconnect(user.id, websocket)


@router.get("/api/agent/commands")
def get_agent_commands(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
):
    query = (
        select(AgentConfig)
        .join(Game, AgentConfig.game_id == Game.id)
        .where(
            AgentConfig.enabled == True,
            AgentConfig.pending_launch_id != None,
            AgentConfig.pending_launch_path != None,
            Game.user_id == agent_user.id,
        )
    )
    configs = session.exec(query).all()
    return {
        "items": [
            {
                "game_id": cfg.game_id,
                "request_id": cfg.pending_launch_id,
                "launch_path": cfg.pending_launch_path,
            }
            for cfg in configs
        ]
    }


@router.post("/api/agent/commands/ack")
def ack_agent_command(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    req: AgentLaunchAckRequest,
):
    config = session.exec(
        select(AgentConfig)
        .join(Game, AgentConfig.game_id == Game.id)
        .where(AgentConfig.game_id == req.game_id, Game.user_id == agent_user.id)
    ).first()
    if not config or not config.pending_launch_id:
        return {"ok": True, "status": "ignored"}

    if config.pending_launch_id != req.request_id:
        return {"ok": True, "status": "ignored"}

    config.last_launch_status = "ok" if req.success else "error"
    config.last_launch_error = None if req.success else (req.error or "Unknown launch error")
    config.last_launch_at = datetime.utcnow()
    config.pending_launch_id = None
    config.pending_launch_path = None
    config.pending_launch_requested_at = None
    config.updated_at = datetime.utcnow()
    session.add(config)
    session.commit()
    WS_MANAGER.notify_commands_updated(agent_user.id)
    return {"ok": True, "status": "acknowledged"}


@router.get("/api/agent/games/{game_id}/notes", response_model=List[NoteRead])
def get_game_notes_for_agent(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    game_id: int,
):
    ensure_owned_game_with_detail(session, agent_user, game_id, "Game not found")
    query = select(Note).where(Note.game_id == game_id).order_by(Note.created_at.desc())
    return session.exec(query).all()


@router.post("/api/agent/games/{game_id}/notes", response_model=NoteRead)
def create_game_note_for_agent(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    game_id: int,
    note: NoteCreate,
):
    ensure_owned_game_with_detail(session, agent_user, game_id, "Game not found")
    db_note = Note.model_validate(note, update={"game_id": game_id})
    session.add(db_note)
    session.commit()
    session.refresh(db_note)
    return db_note


@router.put("/api/agent/notes/{note_id}", response_model=NoteRead)
def update_note_for_agent(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    note_id: int,
    req: AgentNoteUpdateRequest,
):
    db_note = ensure_owned_note_with_detail(session, agent_user, note_id, "Note not found")
    db_note.text = req.text
    session.add(db_note)
    session.commit()
    session.refresh(db_note)
    return db_note


@router.delete("/api/agent/notes/{note_id}")
def delete_note_for_agent(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    note_id: int,
):
    db_note = ensure_owned_note_with_detail(session, agent_user, note_id, "Note not found")
    session.delete(db_note)
    session.commit()
    return {"ok": True}


@router.get("/api/agent/download")
def download_agent():
    base_dir = os.path.dirname(__file__)
    agent_path = os.path.abspath(
        os.path.join(
            base_dir,
            "..",
            "..",
            "..",
            "data",
            "agent",
            "GameTrackerAgent.exe",
        )
    )

    if not os.path.exists(agent_path):
        raise HTTPException(
            status_code=404,
            detail="Агент не найден. Ожидаемый путь: /app/data/agent/GameTrackerAgent.exe",
        )

    return FileResponse(
        agent_path,
        media_type="application/octet-stream",
        filename="GameTrackerAgent.exe",
    )


@router.post("/api/agent/test-ping")
def test_agent_ping(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentTestPingRequest,
):
    game_id = req.game_id
    game = ensure_owned_game_with_detail(session, current_user, game_id, "Игра не найдена")

    if not game.exe_name:
        raise HTTPException(
            status_code=400,
            detail="Для игры не указан исполняемый файл. Укажите его в карточке игры.",
        )

    config = session.exec(
        select(AgentConfig).where(
            AgentConfig.game_id == game_id,
            AgentConfig.enabled == True,
        )
    ).first()

    if not config:
        raise HTTPException(
            status_code=400,
            detail="Агент не настроен для этой игры. Сохраните исполняемый файл в карточке игры.",
        )

    now = datetime.utcnow()
    active_since = now - timedelta(seconds=AGENT_LIVE_HEARTBEAT_TIMEOUT_SECONDS)
    if not current_user.agent_last_seen_at or current_user.agent_last_seen_at < active_since:
        return {
            "ok": False,
            "message": "Агент сейчас не в сети. Запустите агент и попробуйте снова.",
            "exe_name": game.exe_name,
            "status": "agent_inactive",
        }

    session_active_since = now - timedelta(seconds=AGENT_HEARTBEAT_TIMEOUT_SECONDS)
    last_agent_session = session.exec(
        select(DbSession)
        .where(DbSession.game_id == game_id, DbSession.source == "agent")
        .order_by(DbSession.ended_at.desc(), DbSession.started_at.desc())
    ).first()

    if not last_agent_session:
        return {
            "ok": True,
            "message": "Агент в сети. Для этой игры пока нет игровых ping-сессий.",
            "exe_name": game.exe_name,
            "status": "agent_active",
        }

    last_seen = last_agent_session.ended_at or last_agent_session.started_at
    if last_seen < session_active_since:
        return {
            "ok": True,
            "message": "Агент в сети, но текущая игра сейчас не активна.",
            "exe_name": game.exe_name,
            "status": "agent_active",
            "duration_minutes": last_agent_session.duration_minutes,
        }

    return {
        "ok": True,
        "message": "Агент активен: получен недавний ping от запущенного агента.",
        "exe_name": game.exe_name,
        "status": "agent_active",
        "duration_minutes": last_agent_session.duration_minutes,
    }


@router.post("/api/sessions/ping")
def ping_session(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    req: PingRequest,
):
    game = session.get(Game, req.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.user_id != agent_user.id:
        raise HTTPException(status_code=403, detail="Game does not belong to this agent user")

    config = get_agent_config_by_game_id(session, req.game_id)
    if not config or not config.enabled:
        raise HTTPException(status_code=400, detail="Agent config is missing or disabled")

    if req.exe_name.strip().lower() != config.exe_name.strip().lower():
        raise HTTPException(status_code=400, detail="Ping exe_name does not match game config")

    now = datetime.utcnow()
    upsert_agent_session(
        session=session,
        game_id=req.game_id,
        now=now,
        active_source="agent",
        new_source="agent",
        max_gap_seconds=AGENT_SESSION_GAP_SECONDS,
    )
    session.commit()
    return {"ok": True}


@router.get("/api/agent/games", response_model=List[GameRead])
def get_agent_games(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    query = select(Game).where(Game.user_id == current_user.id, Game.sync_type == "non_steam")
    games = session.exec(query).all()
    playtime_map = get_total_playtime_map(session, [game.id for game in games if game.id is not None])
    return [build_game_read(session, game, playtime_map=playtime_map) for game in games]


@router.post("/api/agent/configure", response_model=AgentConfigRead)
def configure_agent(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentConfigRequest,
):
    game_id = req.game_id
    launch_path = normalize_and_validate_launch_path(req.launch_path)
    enabled = req.enabled

    exe_name = extract_exe_name(launch_path)

    game = ensure_owned_game_with_detail(session, current_user, game_id, "Игра не найдена")

    duplicate = session.exec(
        select(AgentConfig)
        .join(Game, AgentConfig.game_id == Game.id)
        .where(
            Game.user_id == current_user.id,
            AgentConfig.game_id != game_id,
            AgentConfig.launch_path == launch_path,
        )
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Этот путь уже используется у другой игры. Укажите уникальный launch_path.",
        )

    game.exe_name = exe_name
    game.launch_path = launch_path
    session.add(game)

    existing = get_agent_config_by_game_id(session, game_id)
    if existing:
        existing.exe_name = exe_name
        existing.launch_path = launch_path
        existing.enabled = enabled
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        WS_MANAGER.notify_snapshot(current_user.id, build_agent_config_items(session, current_user.id))
        return existing

    new_config = AgentConfig(
        game_id=game_id,
        exe_name=exe_name,
        launch_path=launch_path,
        enabled=enabled,
    )
    session.add(new_config)
    session.commit()
    session.refresh(new_config)
    WS_MANAGER.notify_snapshot(current_user.id, build_agent_config_items(session, current_user.id))
    return new_config


@router.post("/api/agent/launch")
def request_agent_launch(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentLaunchRequest,
):
    game = ensure_owned_game_with_detail(session, current_user, req.game_id, "Игра не найдена")

    config = get_agent_config_by_game_id(session, req.game_id)
    if not config or not config.enabled:
        raise HTTPException(status_code=400, detail="Агент не настроен или отключен для этой игры")

    launch_path = normalize_and_validate_launch_path(config.launch_path or game.launch_path or "")
    if not launch_path:
        raise HTTPException(status_code=400, detail="Сначала сохраните путь к исполняемому файлу игры")

    config.pending_launch_id = str(uuid4())
    config.pending_launch_path = launch_path
    config.pending_launch_requested_at = datetime.utcnow()
    config.updated_at = datetime.utcnow()
    session.add(config)
    session.commit()
    WS_MANAGER.notify_commands_updated(current_user.id)

    return {
        "ok": True,
        "message": "Команда запуска отправлена агенту. Убедитесь, что агент запущен.",
        "request_id": config.pending_launch_id,
    }


@router.delete("/api/agent/config/{game_id}")
def delete_agent_config(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    ensure_owned_game_with_detail(session, current_user, game_id, "Игра не найдена")
    config = get_agent_config_by_game_id(session, game_id)

    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")

    session.delete(config)
    session.commit()
    WS_MANAGER.notify_snapshot(current_user.id, build_agent_config_items(session, current_user.id))
    return {"ok": True}
