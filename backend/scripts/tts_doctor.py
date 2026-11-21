"""Why does the game fall back to the browser voice? Checks every step of the voice path.

Run from backend/ with the app running (docker compose ... up, API on :8000):

    uv run python scripts/tts_doctor.py
    uv run python scripts/tts_doctor.py --api http://localhost:8000 --play

1. The Google key and which TTS models it can use.
2. One direct Google call with the app's model and voices (quota or a bad voice shows here).
3. The running app's settings: /healthz.
4. The app's own speech endpoint, GET /tts/{event}?voice=..., on the newest narrated line in the
   database: exactly what the play screen asks for. 200 means you hear Google; 503 means the
   browser speaks instead (the app's answer when Google fails or is cooling down after a 429).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_samples import API, PRESETS, api_key, play, synth  # noqa: E402

APP_MODEL = "gemini-3.8-flash-tts"
APP_VOICES = {"dm": "en-gb-storyteller-4", "buddy": "Sulafat"}


def ok(msg: str) -> None:
    print(f"  OK    {msg}")


def bad(msg: str) -> None:
    print(f"  FAIL  {msg}")


def env_value(name: str, default: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    root = Path(__file__).resolve().parent.parent.parent / ".env"
    if root.exists():
        for line in root.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"') or default
    return default


def get(
    url: str, headers: dict[str, str] | None = None, timeout: float = 60
) -> tuple[int, bytes, float]:
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers or {}), timeout=timeout
        ) as r:
            return r.status, r.read(), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.monotonic() - t0
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode(), time.monotonic() - t0


def newest_lines(db_url: str) -> list[tuple[int, str]]:
    """Newest narrated lines (event id, speaker) from the app's database."""
    import psycopg

    dsn = db_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        rows = conn.execute(
            "SELECT id, coalesce(payload->>'speaker', '') FROM event WHERE type = 'dm_reply' "
            "AND coalesce(payload->>'text', '') <> '' ORDER BY id DESC LIMIT 3"
        ).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


async def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument(
        "--db",
        default=env_value("DATABASE_URL", "postgresql+psycopg://fq:fq@127.0.0.1:5432/financequest"),
    )
    ap.add_argument("--play", action="store_true", help="play the app's audio when it works")
    args = ap.parse_args()
    key = api_key()

    print("1. Google key and TTS models")
    status, body, _ = get(f"{API}/models?pageSize=200", {"x-goog-api-key": key})
    if status != 200:
        bad(f"the key was refused ({status}): {body[:200]!r}")
        return
    models = [
        m["name"].removeprefix("models/") for m in json.loads(body)["models"] if "tts" in m["name"]
    ]
    ok(f"key works; TTS models: {', '.join(models)}")
    (ok if APP_MODEL in models else bad)(
        f"the app's model {APP_MODEL} is {'available' if APP_MODEL in models else 'NOT available'}"
    )

    print("\n2. Direct Google call with the app's model and voices")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(api_version="v1beta"))
    for role, voice in APP_VOICES.items():
        pcm, took, msg = await synth(client, APP_MODEL, voice, PRESETS[role][:80])
        (ok if pcm else bad)(f"{role}: {voice} -> {msg} ({took:.1f}s)")

    print("\n3. The running app")
    status, body, _ = get(f"{args.api}/healthz", timeout=10)
    if status != 200:
        bad(f"{args.api}/healthz answered {status}: is the API running? ({body[:120]!r})")
        return
    health = json.loads(body)
    ok(f"healthz: {health}")
    dm = env_value("TTS_VOICE_DM", "(code default)")
    buddy = env_value("TTS_VOICE_BUDDY", "(code default)")
    fake = env_value("FAKE_LLM", "false")
    print(f"        voices configured in .env: dm={dm}, buddy={buddy}; FAKE_LLM={fake}")
    if env_value("FAKE_LLM", "false").lower() in ("1", "true"):
        bad("FAKE_LLM is on: the app returns silence, so the browser never hears Google")

    print("\n4. The app's speech endpoint (what the play screen calls)")
    try:
        lines = newest_lines(args.db)
    except Exception as exc:  # noqa: BLE001
        bad(f"could not read the database ({exc}); play one turn first, or pass --db")
        return
    if not lines:
        bad("no narrated line in the database yet: start a quest and play one turn first")
        return
    for event_id, speaker in lines:
        for voice in ("dm", "buddy"):
            status, body, took = get(f"{args.api}/tts/{event_id}?voice={voice}", timeout=90)
            if status == 200:
                ok(
                    f"event {event_id} ({speaker or 'narrator'}), voice={voice}: Google audio, "
                    f"{len(body) // 1000} KB in {took:.1f}s"
                )
                if args.play:
                    out = Path("tts-samples")
                    out.mkdir(exist_ok=True)
                    path = out / f"app-{event_id}-{voice}.wav"
                    path.write_bytes(body)
                    play(path)
            elif status == 503:
                bad(
                    f"event {event_id}, voice={voice}: 503 after {took:.1f}s -> the BROWSER voice "
                    "is used (Google failed, timed out, or the app is cooling down after a quota "
                    "error for 5 minutes; check step 2 and the API log)"
                )
            else:
                bad(f"event {event_id}, voice={voice}: {status} {body[:120]!r}")
        break  # the newest line is enough; the others are listed for reference
    print("\nNewest narrated lines:", ", ".join(f"{i} ({s or 'narrator'})" for i, s in lines))


if __name__ == "__main__":
    asyncio.run(main())
