from types import SimpleNamespace

import pytest

from boardbook.parser import claude_client
from boardbook.parser.schema import ExtractedAgenda, ExtractedMeetingMeta


def _fake_extracted() -> ExtractedAgenda:
    return ExtractedAgenda(
        meta=ExtractedMeetingMeta(committee_name="C", meeting_date="2026-01-01", start_time="14:00", location="L"),
        items=[],
    )


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def test_parse_agenda_text_rejects_empty_input():
    with pytest.raises(ValueError, match="empty"):
        claude_client.parse_agenda_text("   ")


def test_parse_agenda_text_returns_parsed_output_and_uses_the_configured_schema(monkeypatch):
    fake_agenda = _fake_extracted()
    fake_client = _FakeClient(SimpleNamespace(stop_reason="end_turn", parsed_output=fake_agenda))
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kwargs: fake_client)

    result = claude_client.parse_agenda_text("Some agenda text", model="claude-opus-5")

    assert result is fake_agenda
    call = fake_client.messages.calls[0]
    assert call["output_format"] is ExtractedAgenda
    assert call["model"] == "claude-opus-5"
    assert call["messages"] == [{"role": "user", "content": "Some agenda text"}]


def test_parse_agenda_text_raises_on_refusal(monkeypatch):
    fake_client = _FakeClient(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kwargs: fake_client)

    with pytest.raises(ValueError, match="declined"):
        claude_client.parse_agenda_text("Some agenda text")


def test_parse_agenda_text_raises_when_no_parsed_output(monkeypatch):
    fake_client = _FakeClient(SimpleNamespace(stop_reason="end_turn", parsed_output=None))
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kwargs: fake_client)

    with pytest.raises(ValueError, match="did not return"):
        claude_client.parse_agenda_text("Some agenda text")


def test_parse_agenda_text_passes_api_key_to_client_only_never_to_environ(monkeypatch):
    """The key regression test for multi-user deployments: a per-call api_key must reach
    the Anthropic client constructor directly and must never be written to os.environ,
    which is process-global and shared by every concurrent Streamlit session."""
    fake_agenda = _fake_extracted()
    fake_client = _FakeClient(SimpleNamespace(stop_reason="end_turn", parsed_output=fake_agenda))
    captured_kwargs = {}

    def fake_constructor(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_client

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", fake_constructor)

    claude_client.parse_agenda_text("Some agenda text", api_key="sk-user-supplied-key")

    assert captured_kwargs.get("api_key") == "sk-user-supplied-key"
    assert "ANTHROPIC_API_KEY" not in __import__("os").environ
