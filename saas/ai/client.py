"""Thin wrapper around the Anthropic SDK: one call, JSON out, one retry on bad JSON."""
from __future__ import annotations

import json
import os


class AIError(RuntimeError):
    pass


def _client():
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AIError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -3]
    return json.loads(cleaned)


def generate_json(system: str, user_message: str, max_tokens: int = 8192) -> dict:
    import anthropic

    client = _client()
    message = user_message
    last_error = None
    for _ in range(2):
        try:
            response = client.messages.create(
                model=_model(),
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": message}],
            )
            text = response.content[0].text
        except anthropic.APIError as e:
            raise AIError(f"Anthropic API call failed: {e}") from e
        except (IndexError, AttributeError) as e:
            raise AIError(f"Anthropic API returned a malformed response: {e}") from e
        try:
            return _extract_json(text)
        except (json.JSONDecodeError, IndexError) as e:
            last_error = e
            message = (
                f"{user_message}\n\nYour previous reply was not valid JSON "
                f"({e}). Reply with ONLY the JSON object, no prose, no fences."
            )
    raise AIError(f"Model did not return valid JSON after retry: {last_error}")
