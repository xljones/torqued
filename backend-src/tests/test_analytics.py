"""Tests for the optional PostHog analytics helper (torqued.analytics)."""

from typing import Any

import pytest

from torqued import analytics


class FakePosthog:
    """Stand-in for posthog.Posthog that records constructor args and captures."""

    instances: list["FakePosthog"] = []

    def __init__(self, api_key: str, host: str) -> None:
        self.api_key = api_key
        self.host = host
        self.calls: list[dict[str, Any]] = []
        FakePosthog.instances.append(self)

    def capture(self, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
        self.calls.append({"distinct_id": distinct_id, "event": event, "properties": properties})


@pytest.fixture
def reset_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test with no cached client and a clean FakePosthog registry."""
    monkeypatch.setattr(analytics, "_client", None)
    FakePosthog.instances.clear()


def test_capture_noop_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch, reset_client: None
) -> None:
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    monkeypatch.setattr(analytics, "Posthog", FakePosthog)

    assert analytics.is_configured() is False
    analytics.capture("u1", "user.logged_in", {"a": 1})  # must not raise or build a client

    assert FakePosthog.instances == []


def test_capture_forwards_and_caches_client(
    monkeypatch: pytest.MonkeyPatch, reset_client: None
) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    monkeypatch.setattr(analytics, "Posthog", FakePosthog)

    assert analytics.is_configured() is True
    analytics.capture(42, "vehicle.created", {"kind": "car"})
    analytics.capture(42, "service_log.created")  # properties defaults to {}

    # Client built once and reused across calls.
    assert len(FakePosthog.instances) == 1
    client = FakePosthog.instances[0]
    assert client.api_key == "phc_test"
    assert client.host == analytics.DEFAULT_HOST
    assert client.calls == [
        {"distinct_id": "42", "event": "vehicle.created", "properties": {"kind": "car"}},
        {"distinct_id": "42", "event": "service_log.created", "properties": {}},
    ]


def test_custom_host(monkeypatch: pytest.MonkeyPatch, reset_client: None) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_HOST", "https://eu.i.posthog.com")
    monkeypatch.setattr(analytics, "Posthog", FakePosthog)

    analytics.capture("u", "user.logged_in")

    assert FakePosthog.instances[0].host == "https://eu.i.posthog.com"
