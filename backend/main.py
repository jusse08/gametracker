import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from database import create_db_and_tables, engine
from auth import get_password_hash
from models import Settings, User
from routers.agent import router as agent_router
from routers.games import router as games_router
from routers.settings import router as settings_router
from routers.users_auth import router as users_auth_router

load_dotenv()

app = FastAPI(title="GameTracker API")


@app.get("/health")
def healthcheck():
    return {"ok": True}


allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
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


app.include_router(users_auth_router)
app.include_router(games_router)
app.include_router(agent_router)
app.include_router(settings_router)
