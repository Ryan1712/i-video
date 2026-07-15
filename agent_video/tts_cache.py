"""Content-hash cache for TTS audio: reuse synthesized speech when the input is unchanged."""
from __future__ import annotations

import hashlib
import json
import os

# Bump whenever TTS behavior changes in a way that makes previously cached audio stale
# (e.g. different post-processing). Old cache entries then simply stop matching.
TTS_CACHE_VERSION = 1


def compute_cache_key(fields: dict) -> str:
    payload = dict(fields)
    payload["cache_version"] = TTS_CACHE_VERSION
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def tts_cache_enabled() -> bool:
    return os.environ.get("TTS_CACHE", "on").strip().lower() not in ("off", "0", "false")
