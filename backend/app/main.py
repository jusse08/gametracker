import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlmodel import Session, select

from app.api.routers.agent import router as agent_router
from app.api.routers.facts import router as facts_router
from app.api.routers.games import router as games_router
from app.api.routers.settings import router as settings_router
from app.api.routers.users_auth import router as users_auth_router
from app.core.auth import get_password_hash
from app.core.database import engine
from app.core.migrations import MIGRATION_COMMAND, ensure_database_schema_current
from app.domain.models import Settings, User

load_dotenv()
logger = logging.getLogger(__name__)

INSECURE_PLACEHOLDER_VALUES = {
    "change-me",
    "change-me-long-random-secret",
    "REPLACE_WITH_A_STRONG_SUPERADMIN_PASSWORD",
    "REPLACE_WITH_A_LONG_RANDOM_SECRET_KEY",
}


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_runtime_security_config() -> None:
    if _is_truthy(os.getenv("ALLOW_INSECURE_DEFAULTS")):
        return

    secret_key = (os.getenv("SECRET_KEY") or "").strip()
    if not secret_key:
        raise RuntimeError("SECRET_KEY is required")
    if secret_key in INSECURE_PLACEHOLDER_VALUES:
        raise RuntimeError("SECRET_KEY must be replaced with a long random value before startup")

    superadmin_password = (os.getenv("SUPERADMIN_PASSWORD") or "").strip()
    if superadmin_password and superadmin_password in INSECURE_PLACEHOLDER_VALUES:
        raise RuntimeError("SUPERADMIN_PASSWORD must be replaced before startup")


def bootstrap_runtime_state() -> None:
    try:
        with Session(engine) as session:
            if not session.get(Settings, 1):
                session.add(Settings(id=1))
                session.commit()

            superadmin_username = os.getenv("SUPERADMIN_USERNAME")
            superadmin_password = os.getenv("SUPERADMIN_PASSWORD")
            if superadmin_username and superadmin_password:
                existing_superadmin = session.exec(
                    select(User).where(User.username == superadmin_username)
                ).first()
                if not existing_superadmin:
                    superadmin = User(
                        username=superadmin_username,
                        hashed_password=get_password_hash(superadmin_password),
                    )
                    session.add(superadmin)
                    session.commit()
    except (OperationalError, ProgrammingError) as exc:
        raise RuntimeError(
            f"Database schema is not initialized. Run '{MIGRATION_COMMAND}' before starting the app."
        ) from exc


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_security_config()
    ensure_database_schema_current(engine)
    bootstrap_runtime_state()
    yield


logging.basicConfig(
    level=getattr(logging, (os.getenv("LOG_LEVEL") or "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title="GameTracker API", lifespan=lifespan)


@app.get("/health")
def healthcheck():
    return {"ok": True}


@app.get("/ready")
def readiness_check(response: Response):
    try:
        with Session(engine) as session:
            session.exec(select(1)).first()
    except SQLAlchemyError:
        logger.warning("Readiness check failed: database unavailable", exc_info=True)
        response.status_code = 503
        return {"ok": False, "detail": "database unavailable"}
    return {"ok": True}


allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def set_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


app.include_router(users_auth_router)
app.include_router(games_router)
app.include_router(facts_router)
app.include_router(agent_router)
app.include_router(settings_router)
