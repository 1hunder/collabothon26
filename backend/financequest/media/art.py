"""Scene art for campaign locations (Nano Banana via Google GenAI).

Prompt = fixed STYLE_GUIDE + scrubbed art_subject + fixed negative block, with the repo
style-anchor image as a reference. One asyncio job per campaign location (timeout + 1 retry)
writes DATA_DIR/art/{campaign}/{location}.webp. A failure keeps the placeholder.
FAKE_LLM=1 writes a tiny generated image with no network.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from PIL import Image
from sqlmodel import Session, select

from financequest.config import get_settings

log = logging.getLogger(__name__)

STYLE_GUIDE = (
    "Painterly fantasy merchant-city illustration. Palette: lapis blue #22305B, "
    "verdigris green #3E8A7E, gilt gold #C9A227, vellum cream #E8DCC2. Warm lantern light "
    "against deep blue shadows. Wide establishing shot, rich architectural detail, soft "
    "brushwork, 16:9 landscape composition."
)
NEGATIVE_BLOCK = (
    "Do not include any logos, text, lettering, signage, banners with writing, people, "
    "faces or figures."
)
STYLE_ANCHOR = Path(__file__).resolve().parent.parent / "fixtures" / "style-anchor.webp"
PLACEHOLDER, PENDING, READY, FAILED = "placeholder", "pending", "ready", "failed"

ImageGenerator = Callable[[str, bytes | None], Awaitable[bytes]]


class ArtRecord(Protocol):
    """The slice of the `location` row the media code touches."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    art_status: str
    art_path: str | None
    art_subject: str | None


def scrub_subject(subject: str, leak_terms: Iterable[str] = ()) -> str:
    """Remove real names/tickers (leak terms) from the subject before it reaches the model."""
    out = subject
    for term in sorted({t for t in leak_terms if t and t.strip()}, key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(term.strip())}(?!\w)", "a grand hall", out, flags=re.I)
    return " ".join(out.split())


def build_art_prompt(subject: str, leak_terms: Iterable[str] = ()) -> str:
    return (
        f"{STYLE_GUIDE}\n\nScene: {scrub_subject(subject, leak_terms)}\n\n{NEGATIVE_BLOCK}\n"
        "Match the style of the attached reference image."
    )


def art_file(campaign_id: uuid.UUID, location_id: uuid.UUID) -> Path:
    return Path(get_settings().data_dir) / "art" / str(campaign_id) / f"{location_id}.webp"


def _to_webp(raw: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=85)
    return buf.getvalue()


async def fake_generate(prompt: str, anchor: bytes | None) -> bytes:
    img = Image.new("RGB", (64, 36), (34, 48, 91))
    buf = io.BytesIO()
    img.save(buf, "WEBP")
    return buf.getvalue()


async def genai_generate(prompt: str, anchor: bytes | None) -> bytes:
    from google import genai
    from google.genai import types

    s = get_settings()
    client = genai.Client(api_key=s.google_genai_api_key)
    contents: list[Any] = [prompt]
    if anchor:
        contents.append(types.Part.from_bytes(data=anchor, mime_type="image/webp"))
    resp = await client.aio.models.generate_content(
        model=s.art_model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="16:9"),
        ),
    )
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else None) or []:
            if part.inline_data and part.inline_data.data:
                return _to_webp(part.inline_data.data)
    raise RuntimeError("image model returned no image")


def default_generator() -> ImageGenerator:
    return fake_generate if get_settings().fake_llm else genai_generate


def _set_status(db: Session, location_id: uuid.UUID, status: str, path: str | None = None) -> None:
    from financequest.db.models_campaign import Location

    loc = db.get(Location, location_id)
    if loc is None:
        return
    loc.art_status = status
    if path is not None:
        loc.art_path = path
    db.add(loc)
    db.commit()


async def run_art_job(
    location_id: uuid.UUID,
    leak_terms: Iterable[str] = (),
    *,
    generator: ImageGenerator | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> str:
    """Generate art for one location. Returns the final art_status."""
    from financequest.db.models_campaign import Location
    from financequest.db.session import get_engine

    s = get_settings()
    make_session = session_factory or (lambda: Session(get_engine()))
    gen = generator or default_generator()
    with make_session() as db:
        loc = db.get(Location, location_id)
        if loc is None or not loc.art_subject:
            return PLACEHOLDER
        campaign_id, subject = loc.campaign_id, loc.art_subject
        _set_status(db, location_id, PENDING)
    prompt = build_art_prompt(subject, leak_terms)
    anchor = STYLE_ANCHOR.read_bytes() if STYLE_ANCHOR.exists() else None
    for attempt in range(1 + s.art_retries):
        try:
            data = await asyncio.wait_for(gen(prompt, anchor), timeout=s.art_timeout_s)
            path = art_file(campaign_id, location_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            with make_session() as db:
                _set_status(db, location_id, READY, str(path))
            return READY
        except Exception:
            log.warning("art job attempt %s failed for %s", attempt + 1, location_id, exc_info=True)
    with make_session() as db:
        _set_status(db, location_id, FAILED)  # keeps the placeholder on the client
    return FAILED


def leak_terms_for_campaign(db: Session, campaign_id: uuid.UUID) -> list[str]:
    from financequest.db.models import ScenarioSecret
    from financequest.db.models_campaign import CampaignRun

    run = db.get(CampaignRun, campaign_id)
    secret = db.get(ScenarioSecret, run.scenario_id) if run else None
    terms = list(secret.leak_terms or []) if secret else []
    if secret:
        terms += [secret.real_name, *([secret.ticker] if secret.ticker else [])]
    return [t for t in terms if isinstance(t, str)]


_tasks: set[asyncio.Task[str]] = set()


def start_art_job(location_id: uuid.UUID, leak_terms: Iterable[str] = ()) -> asyncio.Task[str]:
    task = asyncio.create_task(run_art_job(location_id, list(leak_terms)))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def rescan_pending(
    *,
    generator: ImageGenerator | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> list[str]:
    """At startup: re-run jobs left `pending` by a restart. Returns final statuses."""
    from financequest.db.models_campaign import Location
    from financequest.db.session import get_engine

    make_session = session_factory or (lambda: Session(get_engine()))
    with make_session() as db:
        rows = [
            (loc.id, leak_terms_for_campaign(db, loc.campaign_id))
            for loc in db.exec(select(Location).where(Location.art_status == PENDING)).all()
        ]
    return list(
        await asyncio.gather(
            *(
                run_art_job(i, t, generator=generator, session_factory=session_factory)
                for i, t in rows
            )
        )
    )


async def _safe_rescan() -> str:
    try:
        await rescan_pending()
    except Exception:
        log.warning("art rescan failed", exc_info=True)
    return "done"


def start_rescan() -> asyncio.Task[str]:
    task = asyncio.create_task(_safe_rescan())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task
