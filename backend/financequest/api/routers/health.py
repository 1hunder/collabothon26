from typing import Any

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from financequest.api.deps import DbSession
from financequest.config import get_settings

router = APIRouter(tags=["health"])


def _claude_reachable(api_key: str) -> bool:
    try:
        r = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=5,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/healthz")
def healthz(db: DbSession) -> dict[str, Any]:
    out: dict[str, Any] = {"db": False, "playable_count": 0, "fixtures_loaded": False}
    try:
        db.execute(text("select 1"))
        out["db"] = True
        n = db.execute(text("select count(*) from scenario where status = 'playable'")).scalar()
        out["playable_count"] = int(n or 0)
        out["fixtures_loaded"] = out["playable_count"] > 0
    except Exception:
        out["db"] = False
    key = get_settings().anthropic_api_key
    if key:
        out["claude"] = _claude_reachable(key)
    return out
