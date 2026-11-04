"""Experimental Gemini provider (V3.2 research). Off unless explicitly enabled; never imported by the run path.

Implements the existing `LLMProvider` contract (one system + one user message in, one JSON object out, never
raises) over the native Gemini `models.generateContent` REST method, adding what the research needs:

  * constrained JSON output (`responseMimeType: application/json` + `responseJsonSchema`);
  * token accounting including thinking tokens (`usageMetadata.thoughtsTokenCount`), the served `modelVersion`,
    `finishReason` and the 429 quota identifiers (to tell a free-tier limit from anything else);
  * retries on transport errors, 429 (honouring the server's RetryInfo delay, bounded) and 5xx only.

Configuration (environment only; nothing is read from files):

    GEMINI_ENABLED=false        must be true/1/yes AND a key present, else the provider is disabled
    GEMINI_API_KEY=             sent only in the x-goog-api-key header; never logged, never in a URL or report
    GEMINI_MODEL=gemini-3.5-flash-lite
    GEMINI_TIMEOUT_S=60  GEMINI_MAX_RETRIES=2  GEMINI_MAX_OUTPUT_TOKENS=2048  GEMINI_THINKING_LEVEL=  (MINIMAL|LOW|MEDIUM|HIGH)

The base URL is fixed to Google's endpoint: the model cannot direct a request anywhere else, and the provider has
no tools (no browsing, no URL context, no search grounding).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .provider import LLMProvider, LLMResponse, Transport, parse_json_object, urllib_transport

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_TRUE = {"1", "true", "yes", "on"}
THINKING_LEVELS = ("MINIMAL", "LOW", "MEDIUM", "HIGH")
_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,80}$")


@dataclass(frozen=True)
class GeminiConfig:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    model: str = "gemini-3.5-flash-lite"
    timeout_s: float = 60.0
    max_retries: int = 2
    max_output_tokens: int = 2048
    thinking_level: str | None = None
    max_concurrency: int = 2
    max_response_bytes: int = 262_144
    disabled_reason: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **overrides: Any) -> "GeminiConfig":
        env = os.environ if env is None else env
        get = lambda name, default="": str(env.get(name, default) or "").strip()  # noqa: E731
        values: dict[str, Any] = {
            "api_key": get("GEMINI_API_KEY"),
            "model": get("GEMINI_MODEL", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite",
            "timeout_s": float(get("GEMINI_TIMEOUT_S", "60") or 60),
            "max_retries": min(4, max(0, int(get("GEMINI_MAX_RETRIES", "2") or 2))),
            "max_output_tokens": min(16_000, max(64, int(get("GEMINI_MAX_OUTPUT_TOKENS", "2048") or 2048))),
            "thinking_level": (get("GEMINI_THINKING_LEVEL").upper() or None),
        }
        values.update(overrides)
        reason = None
        if get("GEMINI_ENABLED", "false").casefold() not in _TRUE and not overrides.get("_force_enabled"):
            reason = "GEMINI_ENABLED is not true"
        elif not values["api_key"]:
            reason = "GEMINI_API_KEY is empty"
        elif not _MODEL_RE.match(values["model"]):
            reason = "GEMINI_MODEL is not a plain model code"
        elif values["thinking_level"] not in (None, *THINKING_LEVELS):
            reason = f"GEMINI_THINKING_LEVEL must be one of {', '.join(THINKING_LEVELS)}"
        values.pop("_force_enabled", None)
        return cls(enabled=reason is None, disabled_reason=reason, **values)

    def public(self) -> dict[str, Any]:
        """Settings safe to write into reports (never the key)."""
        return {"enabled": self.enabled, "disabled_reason": self.disabled_reason, "provider": "gemini_generate_content",
                "model": self.model, "timeout_s": self.timeout_s, "max_retries": self.max_retries,
                "max_output_tokens": self.max_output_tokens, "thinking_level": self.thinking_level}


@dataclass
class GeminiResponse(LLMResponse):
    thoughts_tokens: int | None = None
    model_version: str | None = None
    finish_reason: str | None = None
    quota_ids: list[str] = field(default_factory=list)
    retry_delays_s: list[float] = field(default_factory=list)
    raw_text: str | None = None
    error_message: str | None = None  # the API's message, key-redacted, at most 300 characters


def redact(text: str, secret: str) -> str:
    """Remove the key (and anything shaped like a Google key) from a message before it is stored."""
    if secret:
        text = text.replace(secret, "[REDACTED]")
    return re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[REDACTED]", text)


def _retry_delay(details: list[Any]) -> float | None:
    for detail in details:
        if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("RetryInfo"):
            match = re.match(r"^(\d+(?:\.\d+)?)s$", str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def _quota_ids(details: list[Any]) -> list[str]:
    ids = []
    for detail in details:
        if isinstance(detail, dict):
            for violation in detail.get("violations") or []:
                if isinstance(violation, dict) and violation.get("quotaId"):
                    ids.append(str(violation["quotaId"]))
    return ids


class GeminiProvider(LLMProvider):
    name = "gemini"
    enabled = True

    def __init__(self, config: GeminiConfig, transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep,
                 max_retry_delay_s: float = 65.0):
        if not config.enabled:
            raise ValueError(f"GeminiProvider needs an enabled config ({config.disabled_reason})")
        self.config = config
        self.model = config.model
        self.transport = transport or urllib_transport
        self.sleep = sleep
        self.max_retry_delay_s = max_retry_delay_s
        self._slots = threading.BoundedSemaphore(config.max_concurrency)

    def request_body(self, *, system: str, user: str, max_output_tokens: int, response_schema: dict[str, Any] | None,
                     thinking_level: str | None) -> dict[str, Any]:
        generation: dict[str, Any] = {"maxOutputTokens": max_output_tokens, "temperature": 0}
        if response_schema is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseJsonSchema"] = response_schema
        else:
            generation["responseMimeType"] = "application/json"
        level = thinking_level or self.config.thinking_level
        if level and self.config.model.startswith("gemini-2.5"):
            # Gemini 2.5 takes a token budget; thinkingLevel is an error there (API reference, thinkingConfig)
            generation["thinkingConfig"] = {"thinkingBudget": {"MINIMAL": 0, "LOW": 1024, "MEDIUM": 4096, "HIGH": 8192}[level]}
        elif level:
            generation["thinkingConfig"] = {"thinkingLevel": level}
        return {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": generation}

    def complete_json(self, *, system: str, user: str, max_output_tokens: int | None = None, timeout_s: float | None = None,
                      response_schema: dict[str, Any] | None = None, thinking_level: str | None = None) -> GeminiResponse:
        config = self.config
        body = json.dumps(self.request_body(system=system, user=user, max_output_tokens=max_output_tokens or config.max_output_tokens,
                                            response_schema=response_schema, thinking_level=thinking_level)).encode()
        url = f"{BASE_URL}/models/{config.model}:generateContent"
        headers = {"content-type": "application/json", "x-goog-api-key": config.api_key}
        started = time.monotonic()
        budget = timeout_s if timeout_s is not None else (config.timeout_s + self.max_retry_delay_s) * (config.max_retries + 1)
        deadline = started + budget
        error, attempts, quota_ids, delays = "request_failed", 0, [], []
        for attempt in range(config.max_retries + 1):
            timeout = min(config.timeout_s, deadline - time.monotonic())
            if timeout < 1.0:
                error = error if attempts else "no_time_left"
                break
            attempts = attempt + 1
            try:
                with self._slots:
                    status, raw = self.transport(url, headers, body, timeout, config.max_response_bytes)
            except Exception as exc:  # transport errors are retryable; nothing propagates, nothing echoes the key
                status, raw, error = 0, b"", f"transport_{type(exc).__name__}"
            elapsed = int((time.monotonic() - started) * 1000)
            if status == 200:
                return self._parse_ok(raw, attempts, elapsed, quota_ids, delays)
            delay = None
            if status:
                error = f"http_{status}"
                message = None
                try:
                    payload = json.loads(raw or b"{}")
                    details = (payload.get("error") or {}).get("details") or []
                    full = redact(str((payload.get("error") or {}).get("message") or ""), config.api_key)
                    limits = "; ".join(dict.fromkeys(re.findall(r"metric: [\w./]*?(\w+), limit: (\d+)", full) and
                                                     [f"{m} limit {n}" for m, n in re.findall(r"metric: [\w./]*?(\w+), limit: (\d+)", full)]))
                    message = ((f"[{limits}] " if limits else "") + full)[:400] or None
                except (ValueError, AttributeError):
                    details = []
                quota_ids += _quota_ids(details)
                delay = _retry_delay(details)
                if status != 429 and status < 500:
                    return GeminiResponse(ok=False, error=error, attempts=attempts, latency_ms=elapsed, quota_ids=quota_ids, retry_delays_s=delays, error_message=message)
                # a daily (per-day) free-tier quota will not recover by waiting: stop now
                if status == 429 and any("PerDay" in q for q in quota_ids):
                    return GeminiResponse(ok=False, error="http_429_daily_quota", attempts=attempts, latency_ms=elapsed, quota_ids=quota_ids, retry_delays_s=delays, error_message=message)
            if attempt < config.max_retries:
                wait = delay if delay is not None else min(8.0, 1.0 * (2**attempt))
                wait = max(0.0, min(wait + 1.0, self.max_retry_delay_s, deadline - time.monotonic() - 1.0))
                delays.append(round(wait, 2))
                self.sleep(wait)
        return GeminiResponse(ok=False, error=error, attempts=attempts, latency_ms=int((time.monotonic() - started) * 1000),
                              quota_ids=quota_ids, retry_delays_s=delays)

    def _parse_ok(self, raw: bytes, attempts: int, elapsed: int, quota_ids: list[str], delays: list[float]) -> GeminiResponse:
        common = {"attempts": attempts, "latency_ms": elapsed, "response_bytes": len(raw), "quota_ids": quota_ids, "retry_delays_s": delays}
        if len(raw) > self.config.max_response_bytes:
            return GeminiResponse(ok=False, error="response_too_large", **common)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return GeminiResponse(ok=False, error="invalid_envelope_json", **common)
        usage = payload.get("usageMetadata") if isinstance(payload.get("usageMetadata"), dict) else {}
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        first = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        parts = ((first.get("content") or {}).get("parts") or []) if isinstance(first.get("content"), dict) else []
        # thought summaries are never requested; skip any part flagged as a thought
        text = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        meta = {"input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount"),
                "thoughts_tokens": usage.get("thoughtsTokenCount"), "model_version": payload.get("modelVersion"),
                "finish_reason": first.get("finishReason"), "raw_text": text or None}
        if not candidates:
            block = (payload.get("promptFeedback") or {}).get("blockReason")
            return GeminiResponse(ok=False, error=f"no_candidate_{block or 'unknown'}", **common, **meta)
        data = parse_json_object(text) if text else None
        if data is None:
            return GeminiResponse(ok=False, error=f"model_output_not_json_object_{first.get('finishReason') or 'unknown'}", **common, **meta)
        return GeminiResponse(ok=True, data=data, **common, **meta)


def gemini_provider_from_env(env: Mapping[str, str] | None = None, **overrides: Any) -> GeminiProvider | None:
    config = GeminiConfig.from_env(env, **overrides)
    return GeminiProvider(config) if config.enabled else None
