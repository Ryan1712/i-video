"""Content-hash cache for TTS audio: reuse synthesized speech when the input is unchanged."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from typing import Callable

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


logger = logging.getLogger(__name__)


class LocalCacheStore:
    """Cache entries as <root_dir>/<key>.mp3 on the local filesystem."""

    def __init__(self, root_dir: str) -> None:
        self.root_dir = root_dir

    def _entry_path(self, key: str) -> str:
        return os.path.join(self.root_dir, f"{key}.mp3")

    def fetch(self, key: str, dest_path: str) -> bool:
        entry = self._entry_path(key)
        if not os.path.isfile(entry):
            return False
        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        shutil.copyfile(entry, dest_path)
        return True

    def store(self, key: str, src_path: str) -> None:
        os.makedirs(self.root_dir, exist_ok=True)
        shutil.copyfile(src_path, self._entry_path(key))


def synthesize_with_cache(
    key_fields: dict,
    synth_fn: Callable[[str], None],
    out_path: str,
    store,
    force: bool = False,
) -> bool:
    """Fetch cached audio into out_path, or synthesize and store it. Returns True on hit.

    Storage failures are logged and degrade to a miss/no-op; synthesis errors propagate.
    """
    key = compute_cache_key(key_fields)
    if not force:
        try:
            if store.fetch(key, out_path):
                return True
        except Exception as exc:
            logger.warning("TTS cache fetch failed (%s); synthesizing instead", exc)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    synth_fn(out_path)
    try:
        store.store(key, out_path)
    except Exception as exc:
        logger.warning("TTS cache store failed (%s); continuing without caching", exc)
    return False
