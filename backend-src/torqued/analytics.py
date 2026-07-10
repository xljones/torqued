"""PostHog server-side analytics (optional).

Product events are sent to PostHog when ``POSTHOG_API_KEY`` is set. Without the
key the module is inert — :func:`capture` is a no-op — so tests, CI, and
un-provisioned environments never make network calls. Mirrors the optional-
integration shape of :mod:`torqued.mot` (``_config`` / ``is_configured``).

Env vars:
    POSTHOG_API_KEY   PostHog project (write) key; absent → analytics disabled.
    POSTHOG_HOST      Ingestion host; defaults to the US region.
"""

import os
from typing import Any

from posthog import Posthog

DEFAULT_HOST = "https://us.i.posthog.com"

_client: Posthog | None = None


def _api_key() -> str:
    return os.environ.get("POSTHOG_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(_api_key())


def _get_client() -> Posthog | None:
    """Return a cached PostHog client, or None when analytics is disabled."""
    global _client
    if not is_configured():
        return None
    if _client is None:
        host = os.environ.get("POSTHOG_HOST", "").strip() or DEFAULT_HOST
        _client = Posthog(_api_key(), host=host)
    return _client


def capture(distinct_id: Any, event: str, properties: dict[str, Any] | None = None) -> None:
    """Send a product event; a no-op when PostHog isn't configured.

    Best-effort: a PostHog failure must never break the request that triggered
    it, so send errors are swallowed.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.capture(distinct_id=str(distinct_id), event=event, properties=properties or {})
    except Exception:  # pragma: no cover - defensive; analytics must not break a request
        pass
