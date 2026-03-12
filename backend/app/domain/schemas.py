from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class PingRequest(BaseModel):
    game_id: int
    exe_name: str
    timestamp: datetime

class WikiImportRequest(BaseModel):
    url: str

class AgentConfigRequest(BaseModel):
    game_id: int
    launch_path: str
    enabled: bool = True

class AgentTestPingRequest(BaseModel):
    game_id: int

class AgentLaunchRequest(BaseModel):
    game_id: int

class AgentLaunchAckRequest(BaseModel):
    game_id: int
    request_id: str
    success: bool
    error: Optional[str] = None


class GameFactResponse(BaseModel):
    text: str
    game_title: str
    source: str = "fandom"


class FactsRebuildRequest(BaseModel):
    page_url: Optional[str] = None
    game: Optional[str] = None
    seed_urls: Optional[List[str]] = None
    per_seed_limit: int = 60
    max_facts: int = 600
