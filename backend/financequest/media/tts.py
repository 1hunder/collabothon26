"""Gemini TTS: per-sentence synthesis, cached by hash(text, voice) under DATA_DIR/tts.

Only guarded text stored in the event log is ever synthesized. FAKE_LLM=1 returns silence.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import re
import wave
from pathlib import Path
from typing import Literal

from financequest.config import get_settings

Voice = Literal["dm", "buddy"]
SAMPLE_RATE = 24000
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENTENCE.split(text.strip()) if p.strip()]


def voice_name(voice: str) -> str:
    s = get_settings()
    return s.tts_voice_dm if voice == "dm" else s.tts_voice_buddy


def cache_key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}\x00{text}".encode()).hexdigest()


def cache_path(text: str, voice: str) -> Path:
    return Path(get_settings().data_dir) / "tts" / f"{cache_key(text, voice)}.wav"


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def silent_pcm(seconds: float = 0.3) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * seconds)


async def _synth_pcm(sentence: str, voice: str) -> bytes:
    s = get_settings()
    if s.fake_llm:
        return silent_pcm()
    from google import genai

    # Speech generation lives on the Interactions API (generate_content rejects speechConfig).
    client = genai.Client(api_key=s.google_genai_api_key, http_options={"api_version": "v1beta"})
    interaction = await client.aio.interactions.create(
        model=s.tts_model,
        input=[{"type": "user_input", "content": [{"type": "text", "text": sentence}]}],
        response_format={"type": "audio", "mime_type": "audio/l16", "sample_rate": 24000},
        generation_config={"speech_config": [{"voice": voice_name(voice)}]},
    )
    audio = getattr(interaction, "output_audio", None)
    data = getattr(audio, "data", None)
    if data:
        return base64.b64decode(data) if isinstance(data, str) else bytes(data)
    raise RuntimeError("TTS returned no audio")


async def _sentence_wav_pcm(sentence: str, voice: str) -> bytes:
    path = cache_path(sentence, voice)
    if path.exists():
        with wave.open(str(path), "rb") as w:
            return w.readframes(w.getnframes())
    pcm = await _synth_pcm(sentence, voice)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pcm_to_wav(pcm))
    return pcm


async def synthesize(text: str, voice: str) -> bytes:
    """WAV bytes for guarded text; each sentence is synthesized and cached separately."""
    whole = cache_path(text, voice)
    if whole.exists():
        return whole.read_bytes()
    sentences = split_sentences(text) or [text]
    parts = await asyncio.gather(*(_sentence_wav_pcm(x, voice) for x in sentences))
    wav = pcm_to_wav(b"".join(parts))
    whole.parent.mkdir(parents=True, exist_ok=True)
    whole.write_bytes(wav)
    return wav
