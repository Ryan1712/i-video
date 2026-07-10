"""Image generation behind a provider interface. Phase 1: OpenAI gpt-image only."""
from __future__ import annotations

import base64
import os

import requests

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


class ImageError(RuntimeError):
    pass


class GptImageProvider:
    def generate(self, prompt: str) -> bytes:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ImageError("OPENAI_API_KEY not set")
        response = requests.post(
            OPENAI_IMAGES_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": os.environ.get("IMAGE_MODEL", "gpt-image-1"),
                "prompt": prompt,
                "size": os.environ.get("IMAGE_SIZE", "1536x1024"),
            },
            timeout=300,
        )
        if response.status_code != 200:
            raise ImageError(f"Image API failed ({response.status_code}): {response.text[:500]}")
        data = response.json().get("data") or []
        if not data or "b64_json" not in data[0]:
            raise ImageError("Image API returned no image data")
        return base64.b64decode(data[0]["b64_json"])


def get_image_provider() -> GptImageProvider:
    name = os.environ.get("IMAGE_PROVIDER", "gpt-image")
    if name != "gpt-image":
        raise ImageError(f"Unknown IMAGE_PROVIDER: {name}")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ImageError("OPENAI_API_KEY not set")
    return GptImageProvider()
