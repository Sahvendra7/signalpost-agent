"""Reproducible, cached experiment runs (V3.2 research).

Every model response is cached under a content key:
    sha256(model, prompt id, prompt sha, output-schema sha, packet sha, max output tokens, thinking level, stage)
so a repeated run makes no API call, and a run whose responses are all cached needs no network at all
(`provider=None` => cache-only; a miss is recorded as `cache_miss_offline`, never silently replaced).

Each item yields one record with: experiment id, git commit, model, served model version, prompt id/sha, dataset and
item ids, input/output/thinking tokens, the paid-tier-equivalent cost estimate, latency, attempts, retries, errors,
cache hit, the raw model JSON, the validated contract record and the final decision. Failures are records too.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .news_contract import CONTENT_STAGE_SCHEMA, ENTITY_STAGE_SCHEMA, canonical, merge_two_stage, output_schema, render_packet, sha, validate
from .prompts import P4_ENTITY, PromptVersion

# USD per 1M tokens, Gemini Developer API Standard tier, read from the official pricing page on 2026-11-04.
# Output prices include thinking tokens. The project used here is on the Free Tier (verified by a 429 FreeTier quota
# response), so actual spend is $0; these are the costs the same calls would have on a billed project.
PRICES = {
    "gemini-3.8-flash": (0.75, 3.75), "gemini-3.6-flash": (0.75, 3.75), "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-3.5-flash-lite": (0.30, 2.50), "gemini-3.1-flash-lite": (0.25, 1.50), "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}
PRICES_SOURCE = "https://aistudio.google.com/docs/pricing (read 2026-11-04; 3.6/3.8 Flash rise to $1.50/$7.50 on 2027-01-01)"


def paid_cost(model: str, input_tokens: int | None, output_tokens: int | None, thoughts_tokens: int | None) -> float | None:
    price = PRICES.get(model)
    if price is None or input_tokens is None:
        return None
    return round((input_tokens * price[0] + ((output_tokens or 0) + (thoughts_tokens or 0)) * price[1]) / 1_000_000, 8)


def git_commit(root: Path) -> dict[str, Any]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=root, capture_output=True, text=True).stdout.strip()
    return {"commit": head, "src_dirty": bool(dirty)}


class ResponseCache:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.path(key)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        path = self.path(key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(path)


class RateLimiter:
    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            time.sleep(delay)


@dataclass
class Budget:
    max_calls: int
    calls: int = 0
    stop_reason: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self) -> bool:
        with self._lock:
            if self.stop_reason or self.calls >= self.max_calls:
                self.stop_reason = self.stop_reason or "max_calls_reached"
                return False
            self.calls += 1
            return True

    def stop(self, reason: str) -> None:
        with self._lock:
            self.stop_reason = self.stop_reason or reason


def _call(provider: Any, cache: ResponseCache, limiter: RateLimiter, budget: Budget, *, model: str, prompt: PromptVersion, system: str,
          user: str, schema: dict[str, Any], packet_sha: str, stage: str, max_output_tokens: int) -> dict[str, Any]:
    key = sha(canonical({"model": model, "prompt": prompt.id, "prompt_sha": prompt.sha256, "schema": sha(canonical(schema)),
                         "packet": packet_sha, "max_out": max_output_tokens, "think": prompt.thinking_level, "stage": stage}))
    hit = cache.get(key)
    if hit is not None:
        return {**hit, "cache_hit": True, "cache_key": key}
    if provider is None:
        return {"ok": False, "error": "cache_miss_offline", "cache_hit": False, "cache_key": key}
    if not budget.take():
        return {"ok": False, "error": f"not_called_{budget.stop_reason}", "cache_hit": False, "cache_key": key}
    limiter.wait()
    response = provider.complete_json(system=system, user=user, max_output_tokens=max_output_tokens, response_schema=schema,
                                      thinking_level=prompt.thinking_level)
    value = {"ok": response.ok, "data": response.data, "error": response.error, "attempts": response.attempts,
             "latency_ms": response.latency_ms, "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
             "thoughts_tokens": getattr(response, "thoughts_tokens", None), "model_version": getattr(response, "model_version", None),
             "finish_reason": getattr(response, "finish_reason", None), "quota_ids": getattr(response, "quota_ids", []),
             "retry_delays_s": getattr(response, "retry_delays_s", []), "error_message": getattr(response, "error_message", None), "created_at": datetime.now(timezone.utc).isoformat()}
    if response.error == "http_429_daily_quota":
        budget.stop("daily_quota_exhausted")
    if response.ok:
        cache.put(key, value)  # only successful responses are cached; a failure is retried by the next run
    return {**value, "cache_hit": False, "cache_key": key}


def run_items(*, experiment_id: str, dataset: str, packets: list[dict[str, Any]], prompt: PromptVersion, model: str,
              provider: Any, cache: ResponseCache, out_path: Path, root: Path, rpm: float = 10, workers: int = 2,
              max_calls: int = 500, max_output_tokens: int = 1536, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    limiter, budget = RateLimiter(rpm), Budget(max_calls)
    code = git_commit(root)
    schema = output_schema(prompt.evidence_first)

    def one(packet: dict[str, Any]) -> dict[str, Any]:
        user = render_packet(packet)
        calls = []
        if prompt.two_stage:
            content = _call(provider, cache, limiter, budget, model=model, prompt=prompt, system=prompt.system, user=user,
                            schema=CONTENT_STAGE_SCHEMA, packet_sha=packet["packet_sha256"], stage="content", max_output_tokens=max_output_tokens)
            calls.append(content)
            entity = None
            if content.get("ok") and (content.get("data") or {}).get("content_category") in ("genuine_company_news", "press_release_or_announcement", "uncertain"):
                entity = _call(provider, cache, limiter, budget, model=model, prompt=prompt, system=P4_ENTITY, user=user,
                               schema=ENTITY_STAGE_SCHEMA, packet_sha=packet["packet_sha256"], stage="entity", max_output_tokens=max_output_tokens)
                calls.append(entity)
            data = merge_two_stage(content.get("data") if content.get("ok") else None, entity.get("data") if entity and entity.get("ok") else None)
            ok = bool(content.get("ok")) and (entity is None or bool(entity.get("ok")))
            if entity is not None and not entity.get("ok"):
                data = None
        else:
            single = _call(provider, cache, limiter, budget, model=model, prompt=prompt, system=prompt.system, user=user,
                           schema=schema, packet_sha=packet["packet_sha256"], stage="single", max_output_tokens=max_output_tokens)
            calls.append(single)
            data, ok = (single.get("data") if single.get("ok") else None), bool(single.get("ok"))
        record = validate(data, packet) if ok else {"valid": False, "flags": ["api_failure"], "final_decision": "uncertain", "model_decision": None, "quotes": []}
        tokens = {k: sum((c.get(k) or 0) for c in calls) for k in ("input_tokens", "output_tokens", "thoughts_tokens")}
        return {
            "experiment_id": experiment_id, "git": code, "dataset": dataset, "item_id": packet["item_id"],
            "org": packet["target_company"]["organisation_number"], "packet_sha256": packet["packet_sha256"],
            "model": model, "model_version": next((c.get("model_version") for c in calls if c.get("model_version")), None),
            "prompt_id": prompt.id, "prompt_sha256": prompt.sha256, "thinking_level": prompt.thinking_level,
            "calls": len(calls), "api_calls_made": sum(not c.get("cache_hit") and c.get("error") not in ("cache_miss_offline",) and not str(c.get("error") or "").startswith("not_called") for c in calls),
            "cache_hits": sum(bool(c.get("cache_hit")) for c in calls), **tokens,
            "paid_equivalent_cost_usd": paid_cost(model, tokens["input_tokens"] or None, tokens["output_tokens"], tokens["thoughts_tokens"]) if ok else None,
            "latency_ms": sum((c.get("latency_ms") or 0) for c in calls), "attempts": sum((c.get("attempts") or 0) for c in calls),
            "retries": sum(len(c.get("retry_delays_s") or []) for c in calls),
            "errors": [c.get("error") for c in calls if c.get("error")], "error_messages": [c.get("error_message") for c in calls if c.get("error_message")], "quota_ids": sorted({q for c in calls for q in (c.get("quota_ids") or [])}),
            "finish_reasons": [c.get("finish_reason") for c in calls], "ok": ok, "model_output": data, "validated": record,
            "final_decision": record["final_decision"],
        }

    records: list[dict[str, Any]] = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as pool, out_path.open("w", encoding="utf-8") as handle:
        for n, record in enumerate(pool.map(one, packets), 1):
            records.append(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            if progress:
                progress(n, len(packets))
    summary = summarise(records)
    summary.update({"experiment_id": experiment_id, "dataset": dataset, "model": model, "prompt_id": prompt.id,
                    "prompt_sha256": prompt.sha256, "git": code, "budget_stop": budget.stop_reason, "prices_source": PRICES_SOURCE,
                    "finished_at": datetime.now(timezone.utc).isoformat()})
    out_path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter
    n = len(records)
    ok = [r for r in records if r["ok"]]
    fresh = [r for r in ok if r["api_calls_made"]]
    lat = sorted(r["latency_ms"] for r in fresh)
    return {
        "items": n, "ok": len(ok), "api_failures": n - len(ok), "api_failure_rate": round((n - len(ok)) / n, 4) if n else None,
        "errors": dict(Counter(e for r in records for e in r["errors"])),
        "api_calls_made": sum(r["api_calls_made"] for r in records), "cache_hits": sum(r["cache_hits"] for r in records),
        "input_tokens": sum(r["input_tokens"] for r in records), "output_tokens": sum(r["output_tokens"] for r in records),
        "thoughts_tokens": sum(r["thoughts_tokens"] for r in records),
        "paid_equivalent_cost_usd": round(sum(r["paid_equivalent_cost_usd"] or 0 for r in records), 6),
        "latency_ms_p50": lat[len(lat) // 2] if lat else None, "latency_ms_p90": lat[int(len(lat) * 0.9)] if lat else None,
        "retries": sum(r["retries"] for r in records),
        "decisions": dict(Counter(r["final_decision"] for r in records)),
        "model_decisions": dict(Counter(r["validated"].get("model_decision") for r in records)),
        "quotes_total": sum(r["validated"].get("total_quotes", 0) for r in records),
        "quotes_verified": sum(r["validated"].get("verified_quotes", 0) for r in records),
        "quotes_exact": sum(r["validated"].get("exact_quotes", 0) for r in records),
        "flags": dict(Counter(f for r in records for f in r["validated"].get("flags", []))),
        "model_versions": dict(Counter(r["model_version"] for r in records)),
    }
