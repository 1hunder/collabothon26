import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from financequest.db.models import PlayerSession
from financequest.db.session import get_session

DbSession = Annotated[Session, Depends(get_session)]


def require_session(
    db: DbSession, x_session_id: Annotated[str | None, Header()] = None
) -> uuid.UUID:
    try:
        sid = uuid.UUID(x_session_id or "")
    except ValueError:
        raise HTTPException(401, "Missing or invalid X-Session-Id") from None
    if db.get(PlayerSession, sid) is None:
        raise HTTPException(401, "Unknown session")
    return sid


SessionId = Annotated[uuid.UUID, Depends(require_session)]
