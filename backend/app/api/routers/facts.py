from fastapi import APIRouter, Body, Depends, HTTPException

from app.core.auth import get_current_user
from app.domain.models import User
from app.domain.schemas import FactsRebuildRequest, GameFactResponse
from app.integrations.fandom_facts import (
    collect_facts_from_fandom_page,
    collect_fandom_facts,
    fetch_random_fandom_fact,
    save_facts_json,
)
from app.services.common import is_superadmin

router = APIRouter()


@router.get("/api/facts/random", response_model=GameFactResponse)
def read_random_fact(_: User = Depends(get_current_user)):
    try:
        return fetch_random_fandom_fact()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to read facts file") from exc


@router.post("/api/facts/rebuild")
def rebuild_facts(
    payload: FactsRebuildRequest = Body(default_factory=FactsRebuildRequest),
    current_user: User = Depends(get_current_user),
):
    if not is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Only superadmin can rebuild facts")

    if payload.page_url:
        facts = collect_facts_from_fandom_page(
            page_url=payload.page_url,
            game=payload.game,
            max_facts=payload.max_facts,
        )
    else:
        facts = collect_fandom_facts(
            seed_urls=payload.seed_urls,
            per_seed_limit=payload.per_seed_limit,
            max_facts=payload.max_facts,
        )
    destination = save_facts_json(facts)
    return {"ok": True, "count": len(facts), "path": str(destination)}
