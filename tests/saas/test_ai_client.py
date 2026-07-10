import pytest

import saas.ai.client as ai_client
from saas.ai.client import AIError, generate_json


class FakeContent:
    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, text):
        self.content = [FakeContent(text)]


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.replies.pop(0))


class FakeAnthropic:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


def test_returns_parsed_json(monkeypatch):
    fake = FakeAnthropic(['{"script": "hello"}'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    assert generate_json("sys", "user") == {"script": "hello"}


def test_strips_markdown_fences(monkeypatch):
    fake = FakeAnthropic(['```json\n{"a": 1}\n```'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    assert generate_json("sys", "user") == {"a": 1}


def test_retries_once_then_raises(monkeypatch):
    fake = FakeAnthropic(["not json", "still not json"])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    with pytest.raises(AIError):
        generate_json("sys", "user")
    assert len(fake.messages.calls) == 2
    # The retry message must mention the previous failure.
    assert "not valid JSON" in fake.messages.calls[1]["messages"][0]["content"]


def test_model_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
    fake = FakeAnthropic(['{"ok": true}'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    generate_json("sys", "user")
    assert fake.messages.calls[0]["model"] == "claude-test-model"


def test_default_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    fake = FakeAnthropic(['{"ok": true}'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    generate_json("sys", "user")
    assert fake.messages.calls[0]["model"] == "claude-sonnet-5"
