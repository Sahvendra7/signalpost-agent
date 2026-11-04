#!/usr/bin/env python3
"""V3.2 research: run one Gemini news-classification configuration over a packet file (experimental; opt-in).

    # cache-only (default): no network; every miss is recorded as cache_miss_offline
    uv run python scripts/run_gemini_news_experiment.py --packets P.jsonl.gz --prompt news-p2-evidence-v1 \
        --model gemini-3.5-flash-lite --experiment-id X --out OUT.jsonl
    # live: needs --live AND GEMINI_API_KEY in the environment; hard call cap with --max-calls
    ... --live --max-calls 40 --rpm 10

The key is read from the environment only and never printed. Nothing here is used by the release run path.
"""
from __future__ import annotations

import argparse
import dataclasses
import gzip
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.llm.gemini import GeminiConfig, GeminiProvider  # noqa: E402
from norway_company_agent.llm_experiments.prompts import PROMPTS  # noqa: E402
from norway_company_agent.llm_experiments.runner import ResponseCache, run_items  # noqa: E402

DEFAULT_CACHE = ROOT / "measurements/v32-gemini-2026-11-04/cache"


def load_packets(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--packets", required=True, type=Path)
    p.add_argument("--prompt", required=True, choices=sorted(PROMPTS))
    p.add_argument("--model", required=True)
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--dataset", default=None)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--only", type=Path, help="file with one item_id per line to restrict to")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--live", action="store_true", help="allow API calls (otherwise cache-only)")
    p.add_argument("--max-calls", type=int, default=0, help="hard cap on API calls in this run (required with --live)")
    p.add_argument("--rpm", type=float, default=10)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--max-output-tokens", type=int, default=1536)
    p.add_argument("--thinking", choices=["MINIMAL", "LOW", "MEDIUM", "HIGH"], help="override the prompt's thinking level (new prompt id)")
    args = p.parse_args()

    packets = load_packets(args.packets)
    if args.only:
        wanted = [line.strip() for line in args.only.read_text(encoding="utf-8").splitlines() if line.strip()]
        index = {pk["item_id"]: pk for pk in packets}
        packets = [index[i] for i in wanted if i in index]
    if args.limit:
        packets = packets[: args.limit]
    prompt = PROMPTS[args.prompt]
    if args.thinking and args.thinking != prompt.thinking_level:
        prompt = dataclasses.replace(prompt, id=f"{prompt.id}+think-{args.thinking.lower()}", thinking_level=args.thinking)
    provider = None
    if args.live:
        if args.max_calls <= 0:
            raise SystemExit("--live needs an explicit --max-calls budget")
        config = GeminiConfig.from_env(os.environ, model=args.model, _force_enabled=True)
        if not config.enabled:
            raise SystemExit(f"Gemini not configured: {config.disabled_reason}")
        provider = GeminiProvider(config)
    summary = run_items(experiment_id=args.experiment_id, dataset=args.dataset or args.packets.name.split(".")[0], packets=packets,
                        prompt=prompt, model=args.model, provider=provider, cache=ResponseCache(args.cache),
                        out_path=args.out, root=ROOT, rpm=args.rpm, workers=args.workers, max_calls=args.max_calls or 0,
                        max_output_tokens=args.max_output_tokens,
                        progress=lambda n, t: print(f"  {n}/{t}", file=sys.stderr, flush=True) if n % 25 == 0 or n == t else None)
    print(json.dumps({k: summary[k] for k in ("experiment_id", "items", "ok", "api_failures", "api_calls_made", "cache_hits", "input_tokens",
                                             "output_tokens", "thoughts_tokens", "paid_equivalent_cost_usd", "latency_ms_p50", "decisions",
                                             "errors", "budget_stop", "quotes_total", "quotes_verified")}, indent=1))


if __name__ == "__main__":
    main()
