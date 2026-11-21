import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from financequest.api.deps import DbSession
from financequest.db.models import PlayerSession

router = APIRouter(tags=["session"])


class SessionOut(BaseModel):
    session_id: uuid.UUID


@router.post("/session", response_model=SessionOut, status_code=201)
def create_session(db: DbSession) -> SessionOut:
    s = PlayerSession()
    db.add(s)
    db.commit()
    return SessionOut(session_id=s.id)
