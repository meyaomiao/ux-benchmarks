"""Single entry point for OpenAI-compatible relay calls.

Every LLM call in the project goes through one relay (``settings.gpt_base_url``)
with one model (``settings.gpt_scorer_model``). This module holds the request
plumbing that the M0/M1/M2/L3/L5 generators used to duplicate as inline
``anthropic`` clients.

Callers own their own fallback: ``chat`` raises on any failure so each service
keeps its existing "log a warning, return the deterministic mock" behaviour.
"""
from __future__ import annotations

import json
import urllib.request

from app.core.config import settings


def relay_available() -> bool:
    """True when a real relay call can be attempted."""
    return bool(settings.gpt_api_key)


def chat(
    system: str,
    prompt: str,
    max_tokens: int = 2048,
    timeout: int = 60,
    model: str | None = None,
) -> str:
    """Return the assistant text for a single-turn system+user exchange.

    Raises on transport errors, non-200 responses and malformed payloads.
    """
    body = json.dumps({
        "model": model or settings.gpt_scorer_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        f"{settings.gpt_base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.gpt_api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    return (payload["choices"][0]["message"]["content"] or "").strip()
