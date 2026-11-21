"""Listen to Google Gemini TTS voices directly (no app, no browser fallback involved).

Run from backend/:

    uv run python scripts/tts_samples.py                       # the app's voices, play them
    uv run python scripts/tts_samples.py --voices Charon,Algenib,en-gb-storyteller-4 --preset dm
    uv run python scripts/tts_samples.py --models gemini-3.8-flash-tts,gemini-2.5-flash-preview-tts
    uv run python scripts/tts_samples.py --text "Your own line." --voices Sulafat --no-play
    uv run python scripts/tts_samples.py --list --lang en-GB --search storyteller

The key comes from GOOGLE_GENAI_API_KEY (environment, else backend/.env or the repo's .env).
WAV files go to tts-samples/ (gitignored scratch output); on Windows they also play in turn.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import sys
import time
import urllib.request
import wave
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
SAMPLE_RATE = 24000
PRESETS = {
    "dm": "Rain taps the stained glass of the Guild Archive. You open the annual ledger: sales "
    "climbing, yet coin draining from the treasury. A broker waits at the counter. What do you do "
    "with your coins?",
    "buddy": "Good question! A cash flow statement shows the money that actually moved, not just "
    "what the books promise.",
    "news": "Breaking news from the Grand Exchange: the Golden Guild reports a heavy loss, and its "
    "owners' claim shrinks by a fortune overnight.",
}
DEFAULT_VOICES = {"dm": "en-gb-storyteller-4", "buddy": "Sulafat", "news": "en-gb-storyteller-4"}


def api_key() -> str:
    key = os.environ.get("GOOGLE_GENAI_API_KEY", "").strip()
    if key:
        return key
    here = Path(__file__).resolve().parent.parent
    for env in (here / ".env", here.parent / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_GENAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    sys.exit("GOOGLE_GENAI_API_KEY is not set (environment or .env)")


def list_voices(key: str, lang: str | None, search: str | None) -> None:
    """Prints the voice catalogue, filtered by language and a free-text search."""
    voices, token = [], None
    while True:
        url = f"{API}/voices?pageSize=200" + (f"&pageToken={token}" if token else "")
        req = urllib.request.Request(url, headers={"x-goog-api-key": key})
        data = json.load(urllib.request.urlopen(req, timeout=30))
        voices += data.get("voices", [])
        token = data.get("next_page_token") or data.get("nextPageToken")
        if not token:
            break
    rows = [
        v for v in voices
        if (not lang or v["language_code"].lower() == lang.lower())
        and (not search or search.lower() in json.dumps(v).lower())
    ]  # fmt: skip
    for v in rows:
        print(f"{v['id']:26} {v['language_code']:6} {v['gender']:7} {v['persona'][:30]:30} "
              f"{v['description'][:90]}")  # fmt: skip
    print(f"\n{len(rows)} of {len(voices)} voices")


def to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def explain(exc: Exception) -> str:
    text = str(exc)
    if "429" in text[:300] or "RESOURCE_EXHAUSTED" in text[:300]:
        return (
            "QUOTA (429): the free tier is used up for now; the app would fall back to the browser"
        )
    if "404" in text[:300]:
        return "NOT FOUND (404): this model or voice is not available to this key"
    if "403" in text[:300] or "PERMISSION" in text[:300]:
        return "FORBIDDEN (403): the key cannot use this model"
    return f"{type(exc).__name__}: {text[:200]}"


async def synth(client, model: str, voice: str, text: str) -> tuple[bytes | None, float, str]:
    """One call, the same way the app makes it (Interactions API, 24 kHz linear PCM)."""
    t0 = time.monotonic()
    try:
        it = await client.aio.interactions.create(
            model=model,
            input=[{"type": "user_input", "content": [{"type": "text", "text": text}]}],
            response_format={"type": "audio", "mime_type": "audio/l16", "sample_rate": SAMPLE_RATE},
            generation_config={"speech_config": [{"voice": voice}]},
        )
        data = it.output_audio.data
        pcm = base64.b64decode(data) if isinstance(data, str) else bytes(data)
        return pcm, time.monotonic() - t0, "ok"
    except Exception as exc:  # noqa: BLE001 - reported per sample
        return None, time.monotonic() - t0, explain(exc)


def play(path: Path) -> None:
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    else:
        print(f"   (play it with any audio player: {path})")


async def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--list", action="store_true", help="list the voice catalogue and exit")
    ap.add_argument("--lang", help="with --list: language code, e.g. en-GB")
    ap.add_argument("--search", help="with --list: free-text filter, e.g. storyteller")
    ap.add_argument(
        "--voices", help="comma-separated voice ids (default: the app's voice per preset)"
    )
    ap.add_argument("--models", default=DEFAULT_MODEL, help="comma-separated TTS models")
    ap.add_argument(
        "--preset", choices=sorted(PRESETS), help="one preset line (default: dm and buddy)"
    )
    ap.add_argument("--text", help="your own line instead of the presets")
    ap.add_argument("--out", default="tts-samples", help="output folder")
    ap.add_argument("--no-play", action="store_true", help="only write the WAV files")
    args = ap.parse_args()

    key = api_key()
    if args.list:
        list_voices(key, args.lang, args.search)
        return

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(api_version="v1beta"))
    if args.text:
        lines = [("custom", args.text)]
    elif args.preset:
        lines = [(args.preset, PRESETS[args.preset])]
    else:
        lines = [("dm", PRESETS["dm"]), ("buddy", PRESETS["buddy"])]
    jobs = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        for name, text in lines:
            voices = (
                args.voices.split(",") if args.voices else [DEFAULT_VOICES.get(name, "Sulafat")]
            )
            jobs += [(model, v.strip(), name, text) for v in voices if v.strip()]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = await asyncio.gather(*(synth(client, m, v, t) for m, v, _, t in jobs))
    print(f"{'model':32} {'voice':22} {'line':7} {'time':>6} {'audio':>6}  result")
    files = []
    for (model, voice, name, _), (pcm, took, status) in zip(jobs, results, strict=True):
        secs = f"{len(pcm) / (2 * SAMPLE_RATE):.1f}s" if pcm else "-"
        print(f"{model:32} {voice:22} {name:7} {took:5.1f}s {secs:>6}  {status}")
        if pcm:
            path = out / f"{model}__{voice}__{name}.wav"
            path.write_bytes(to_wav(pcm))
            files.append((path, model, voice))
    print(f"\nWAV files in {out.resolve()}")
    if not args.no_play:
        for path, model, voice in files:
            print(f"▶ {voice} ({model})")
            play(path)


if __name__ == "__main__":
    asyncio.run(main())
