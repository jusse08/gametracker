from datetime import datetime
from typing import Optional
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
