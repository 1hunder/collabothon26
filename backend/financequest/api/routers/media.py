import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from financequest.api.deps import DbSession
from financequest.db.models import Event
from financequest.db.models_campaign import Location
from financequest.media import tts

router = APIRouter(tags=["media"])


@router.get("/locations/{location_id}/art")
def location_art(location_id: uuid.UUID, db: DbSession) -> FileResponse:
    """Unguessable UUID; `<img>` cannot send headers, so no session header here."""
    loc = db.get(Location, location_id)
    if loc is None or loc.art_status != "ready" or not loc.art_path:
        raise HTTPException(404, "No art")
    path = Path(loc.art_path)
    if not path.is_file():
        raise HTTPException(404, "No art")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "max-age=86400"})


@router.get("/tts/{audio_text_id}")
async def speak(audio_text_id: int, voice: Literal["dm", "buddy"], db: DbSession) -> Response:
    """Audio for the stored, guarded text of an event; never for client-supplied text."""
    event = db.get(Event, audio_text_id)
    text = event.payload.get("text") if event and isinstance(event.payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(404, "Unknown audio text")
    try:
        wav = await tts.synthesize(text, voice)
    except tts.TtsUnavailable:
        raise HTTPException(503, "Voice unavailable") from None
    return Response(wav, media_type="audio/wav", headers={"Cache-Control": "max-age=86400"})
