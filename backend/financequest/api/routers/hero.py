from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from financequest.api.deps import DbSession, SessionId
from financequest.api.errors import ApiError
from financequest.campaign import rules, service
from financequest.db.models_campaign import Hero

router = APIRouter(tags=["hero"])


class HeroIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    hero_class: Literal["guardian", "analyst", "investigator"] = Field(alias="class")


@router.get("/hero")
def get_hero(db: DbSession, sid: SessionId) -> dict[str, object]:
    hero = service.get_hero(db, sid)
    if hero is None:
        raise ApiError(404, "no_hero", "No hero yet")
    return service.hero_out(db, hero, service.ensure_player(db, sid))


@router.post("/hero", status_code=201)
def create_hero(body: HeroIn, db: DbSession, sid: SessionId) -> dict[str, object]:
    player = service.ensure_player(db, sid)
    if service.get_hero(db, sid) is not None:
        raise ApiError(409, "hero_exists", "A hero already exists")
    name = rules.normalize_name(body.name)
    if name is None:
        raise ApiError(422, "invalid_name", "Name must be 2–20 characters.")
    hero = Hero(player_id=sid, name=name, hero_class=body.hero_class)
    db.add(hero)
    db.commit()
    return service.hero_out(db, hero, player)
