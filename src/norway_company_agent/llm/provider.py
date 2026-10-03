"""Optional, provider-agnostic LLM access. Off unless explicitly configured.

    LLMProvider
    ├── DisabledProvider      default; never makes a request
    └── ConfigurableProvider  any endpoint speaking one of two common wire formats

No provider, model or URL is hard-coded. Configuration comes from the environment:

    LLM_ENABLED=false                 must be true/1/yes AND model, base URL and key present
    LLM_MODEL=                        model identifier, passed through verbatim
    LLM_API_KEY=                      never logged or written to any output
    LLM_BASE_URL=                     e.g. https://host/v1 (the wire path is appended)
    LLM_API_FORMAT=openai_chat        openai_chat (POST {base}/chat/completions) | anthropic_messages (POST {base}/messages)
    LLM_TIMEOUT_S=20                  per request
    LLM_MAX_RETRIES=1                 extra attempts on transport errors, 429 and 5xx only
    LLM_MAX_CONCURRENCY=2             simultaneous requests across all batch workers
    LLM_MAX_RESPONSE_BYTES=65536      larger responses are discarded unread
    LLM_MAX_OUTPUT_TOKENS=1200
    LLM_MAX_INPUT_CHARS=12000         page text sent per extraction call
    LLM_MAX_CALLS_PER_COMPANY=2
    LLM_MAX_CALLS_PER_RUN=1000
    LLM_COMPANY_BUDGET_S=60           LLM wall time per company
    LLM_SYNTHESIS=verified_site       verified_site | all | off

A provider never raises: every failure is an `LLMResponse` with `ok=False` and an error code, so the
caller can fall back to the deterministic result.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

API_FORMATS = ("openai_chat", "anthropic_messages")
SYNTHESIS_MODES = ("verified_site", "all", "off")
_TRUE = {"1", "true", "yes", "on"}

# transport(url, headers, body, timeout_s, max_bytes) -> (http_status, response_bytes); may raise.
Transport = Callable[[str, dict[str, str], bytes, float, int], tuple[int, bytes]]


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    model: str = ""
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    api_format: str = "openai_chat"
    timeout_s: float = 20.0
    max_retries: int = 1
    max_concurrency: int = 2
    max_response_bytes: int = 65_536
    max_output_tokens: int = 1_200
    max_input_chars: int = 12_000
    max_calls_per_company: int = 2
    max_calls_per_run: int = 1_000
    company_budget_s: float = 60.0
    synthesis: str = "verified_site"
    disabled_reason: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMConfig":
        env = os.environ if env is None else env
        get = lambda name, default="": str(env.get(name, default) or "").strip()  # noqa: E731

        def number(name: str, default: float, kind: type = int) -> Any:
            try:
                return kind(get(name, str(default)))
            except ValueError:
                return default

        values = {
            "model": get("LLM_MODEL"),
            "api_key": get("LLM_API_KEY"),
            "base_url": get("LLM_BASE_URL").rstrip("/"),
            "api_format": get("LLM_API_FORMAT", "openai_chat") or "openai_chat",
            "timeout_s": max(1.0, number("LLM_TIMEOUT_S", 20.0, float)),
            "max_retries": min(3, max(0, number("LLM_MAX_RETRIES", 1))),
            "max_concurrency": min(16, max(1, number("LLM_MAX_CONCURRENCY", 2))),
            "max_response_bytes": min(1_000_000, max(1_024, number("LLM_MAX_RESPONSE_BYTES", 65_536))),
            "max_output_tokens": min(8_000, max(64, number("LLM_MAX_OUTPUT_TOKENS", 1_200))),
            "max_input_chars": min(60_000, max(1_000, number("LLM_MAX_INPUT_CHARS", 12_000))),
            "max_calls_per_company": min(2, max(0, number("LLM_MAX_CALLS_PER_COMPANY", 2))),
            "max_calls_per_run": max(0, number("LLM_MAX_CALLS_PER_RUN", 1_000)),
            "company_budget_s": max(1.0, number("LLM_COMPANY_BUDGET_S", 60.0, float)),
            "synthesis": get("LLM_SYNTHESIS", "verified_site") or "verified_site",
        }
        reason = None
        if get("LLM_ENABLED", "false").casefold() not in _TRUE:
            reason = "LLM_ENABLED is not true"
        elif not values["model"]:
            reason = "LLM_MODEL is empty"
        elif not values["base_url"]:
            reason = "LLM_BASE_URL is empty"
        elif not values["base_url"].startswith(("https://", "http://")):
            reason = "LLM_BASE_URL is not an http(s) URL"
        elif not values["api_key"]:
            reason = "LLM_API_KEY is empty"
        elif values["api_format"] not in API_FORMATS:
            reason = f"LLM_API_FORMAT must be one of {', '.join(API_FORMATS)}"
        elif values["synthesis"] not in SYNTHESIS_MODES:
            reason = f"LLM_SYNTHESIS must be one of {', '.join(SYNTHESIS_MODES)}"
        return cls(enabled=reason is None, disabled_reason=reason, **values)

    def public(self) -> dict[str, Any]:
        """Settings safe to write into reports (never the key)."""
        return {
            "enabled": self.enabled, "disabled_reason": self.disabled_reason, "model": self.model or None,
            "base_url_host": re.sub(r"^https?://([^/]+).*$", r"\1", self.base_url) if self.base_url else None,
            "api_format": self.api_format, "timeout_s": self.timeout_s, "max_retries": self.max_retries,
            "max_concurrency": self.max_concurrency, "max_response_bytes": self.max_response_bytes,
            "max_output_tokens": self.max_output_tokens, "max_input_chars": self.max_input_chars,
            "max_calls_per_company": self.max_calls_per_company, "max_calls_per_run": self.max_calls_per_run,
            "company_budget_s": self.company_budget_s, "synthesis": self.synthesis,
        }


@dataclass
class LLMResponse:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    response_bytes: int = 0


class LLMProvider(ABC):
    """Narrow interface: one system + one user message in, one JSON object out. Never raises."""

    name = "abstract"
    enabled = False
    model: str | None = None

    @abstractmethod
    def complete_json(self, *, system: str, user: str, max_output_tokens: int | None = None, timeout_s: float | None = None) -> LLMResponse:
        raise NotImplementedError


class DisabledProvider(LLMProvider):
    name = "disabled"
    enabled = False

    def __init__(self, reason: str = "LLM disabled"):
        self.reason = reason

    def complete_json(self, *, system: str, user: str, max_output_tokens: int | None = None, timeout_s: float | None = None) -> LLMResponse:
        return LLMResponse(ok=False, error="disabled", attempts=0)


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout_s: float, max_bytes: int) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return response.status, response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(max_bytes + 1)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """The model's text as one JSON object; tolerates a ```json fence, nothing else."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.S)
    if fenced:
        stripped = fenced.group(1)
    try:
        value = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


class ConfigurableProvider(LLMProvider):
    name = "configurable"
    enabled = True

    def __init__(self, config: LLMConfig, transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep):
        if not config.enabled:
            raise ValueError(f"ConfigurableProvider needs an enabled config ({config.disabled_reason})")
        self.config = config
        self.model = config.model
        self.transport = transport or urllib_transport
        self.sleep = sleep
        self._slots = threading.BoundedSemaphore(config.max_concurrency)

    def _request(self, system: str, user: str, max_output_tokens: int) -> tuple[str, dict[str, str], bytes]:
        config = self.config
        if config.api_format == "anthropic_messages":
            body = {"model": config.model, "max_tokens": max_output_tokens, "temperature": 0, "system": system, "messages": [{"role": "user", "content": user}]}
            headers = {"content-type": "application/json", "x-api-key": config.api_key, "anthropic-version": "2023-06-01"}
            return f"{config.base_url}/messages", headers, json.dumps(body).encode()
        body = {"model": config.model, "max_tokens": max_output_tokens, "temperature": 0, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"content-type": "application/json", "authorization": f"Bearer {config.api_key}"}
        return f"{config.base_url}/chat/completions", headers, json.dumps(body).encode()

    def _read(self, payload: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        if self.config.api_format == "anthropic_messages":
            blocks = payload.get("content") if isinstance(payload.get("content"), list) else []
            text = "".join(str(block.get("text") or "") for block in blocks if isinstance(block, dict) and block.get("type") == "text")
            return text or None, usage.get("input_tokens"), usage.get("output_tokens")
        choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
        message = (choices[0] or {}).get("message") if choices and isinstance(choices[0], dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        return (text if isinstance(text, str) and text else None), usage.get("prompt_tokens"), usage.get("completion_tokens")

    def complete_json(self, *, system: str, user: str, max_output_tokens: int | None = None, timeout_s: float | None = None) -> LLMResponse:
        config = self.config
        url, headers, body = self._request(system, user, max_output_tokens or config.max_output_tokens)
        # `timeout_s` bounds the whole call, retries included; each attempt also stops at config.timeout_s.
        started = time.monotonic()
        deadline = started + (timeout_s if timeout_s is not None else config.timeout_s * (config.max_retries + 1))
        error = "request_failed"
        attempts = 0
        for attempt in range(config.max_retries + 1):
            timeout = min(config.timeout_s, deadline - time.monotonic())
            if timeout < 1.0:
                error = error if attempts else "no_time_left"
                break
            attempts = attempt + 1
            try:
                with self._slots:
                    status, raw = self.transport(url, headers, body, timeout, config.max_response_bytes)
            except Exception as exc:  # transport errors are retryable; nothing propagates
                status, raw, error = 0, b"", f"transport_{type(exc).__name__}"
            elapsed = int((time.monotonic() - started) * 1000)
            if status == 200:
                if len(raw) > config.max_response_bytes:
                    return LLMResponse(ok=False, error="response_too_large", attempts=attempts, latency_ms=elapsed, response_bytes=len(raw))
                try:
                    payload = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    return LLMResponse(ok=False, error="invalid_envelope_json", attempts=attempts, latency_ms=elapsed, response_bytes=len(raw))
                text, input_tokens, output_tokens = self._read(payload if isinstance(payload, dict) else {})
                data = parse_json_object(text) if text else None
                if data is None:
                    return LLMResponse(ok=False, error="model_output_not_json_object", attempts=attempts, latency_ms=elapsed, input_tokens=input_tokens, output_tokens=output_tokens, response_bytes=len(raw))
                return LLMResponse(ok=True, data=data, attempts=attempts, latency_ms=elapsed, input_tokens=input_tokens, output_tokens=output_tokens, response_bytes=len(raw))
            if status:
                error = f"http_{status}"
                if status != 429 and status < 500:
                    return LLMResponse(ok=False, error=error, attempts=attempts, latency_ms=elapsed)
            if attempt < config.max_retries:
                self.sleep(max(0.0, min(4.0, 0.5 * (2**attempt), deadline - time.monotonic() - 1.0)))
        return LLMResponse(ok=False, error=error, attempts=attempts, latency_ms=int((time.monotonic() - started) * 1000))


def provider_from_config(config: LLMConfig, transport: Transport | None = None) -> LLMProvider:
    return ConfigurableProvider(config, transport=transport) if config.enabled else DisabledProvider(config.disabled_reason or "LLM disabled")
