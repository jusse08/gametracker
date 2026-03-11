from datetime import datetime
from pydantic import BaseModel

class PingRequest(BaseModel):
    game_id: int
    timestamp: datetime

class WikiImportRequest(BaseModel):
    url: str
