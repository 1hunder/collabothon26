import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from financequest.api.deps import DbSession
from financequest.db.models import Event
from financequest.db.models_campaign import Location
from financequest.media import tts
from financequest.storage import get_storage

router = APIRouter(tags=["media"])


@router.get("/locations/{location_id}/art")
def location_art(location_id: uuid.UUID, db: DbSession) -> Response:
    """Unguessable UUID; `<img>` cannot send headers, so no session header here."""
    loc = db.get(Location, location_id)
    if loc is None or loc.art_status != "ready" or not loc.art_path:
        raise HTTPException(404, "No art")
    headers = {"Cache-Control": "max-age=86400"}
    legacy = Path(loc.art_path)  # rows written before the storage layer hold an absolute path
    if legacy.is_absolute() and legacy.is_file():
        return FileResponse(legacy, media_type="image/webp", headers=headers)
    store = get_storage()
    try:
        data = store.get_bytes(loc.art_path) if store.exists(loc.art_path) else None
    except ValueError:
        data = None
    if data is None:
        raise HTTPException(404, "No art")
    return Response(data, media_type="image/webp", headers=headers)


@router.get("/tts/{audio_text_id}")
async def speak(
    audio_text_id: str, voice: Literal["dm", "buddy", "veteran"], db: DbSession
) -> Response:
    """Audio for the stored, guarded text of an event (``123``) or a Veteran reply (``v123``);
    never for client-supplied text."""
    text: object = None
    if audio_text_id.startswith("v") and audio_text_id[1:].isdigit():
        from financequest.veteran.service import spoken_text

        text = spoken_text(db, int(audio_text_id[1:]))
    elif audio_text_id.isdigit():
        event = db.get(Event, int(audio_text_id))
        text = event.payload.get("text") if event and isinstance(event.payload, dict) else None
    else:
        raise HTTPException(422, "Audio ids are stored reply ids")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(404, "Unknown audio text")
    try:
        audio = await tts.open_audio(text, voice)
    except tts.TtsUnavailable:
        raise HTTPException(503, "Voice unavailable") from None
    if isinstance(audio, bytes):
        return Response(audio, media_type="audio/wav", headers={"Cache-Control": "max-age=86400"})
    # Still being made: stream it, so the voice starts with the first chunk (about 3 s) instead
    # of after the whole reply. Not cached by the browser: a cut-off stream must not stick.
    return StreamingResponse(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
