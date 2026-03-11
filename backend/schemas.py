from datetime import datetime
from pydantic import BaseModel

class PingRequest(BaseModel):
    game_id: int
    timestamp: datetime

class WikiImportRequest(BaseModel):
    url: str

class AgentConfigRequest(BaseModel):
    game_id: int
    exe_name: str
    enabled: bool = True

class AgentTestPingRequest(BaseModel):
    game_id: int
