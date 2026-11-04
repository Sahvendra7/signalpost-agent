"""Replay through a clean release tree and log every withheld news/social/job candidate with its reason.

    cd <clean tree> && uv run python <this file> REASONS.jsonl <replay_run.py args>

The release code is not modified: SiteFacts.reject is wrapped at runtime to also append one JSON row per call
(the org is remembered thread-locally from site_facts.is_publisher(profile), which extract_site_facts calls first).
"""
import json, runpy, sys, threading
sys.path.insert(0, "src")
import norway_company_agent.site_facts as sf

OUT = open(sys.argv[1], "a", encoding="utf-8")
LOCK = threading.Lock()
orig_reject = sf.SiteFacts.reject
orig_is_publisher = sf.is_publisher
CURRENT = threading.local()


def is_publisher(profile):
    # called by extract_site_facts (module-global lookup) before the news candidates are judged: remember the org
    CURRENT.org = (profile or {}).get("organisation_number") or ((profile or {}).get("input") or {}).get("organisation_number")
    return orig_is_publisher(profile)


def reject(self, kind, reason, item, page):
    orig_reject(self, kind, reason, item, page)
    if kind in ("activity", "social", "job"):
        row = {"org": getattr(CURRENT, "org", None), "kind": kind, "reason": reason, "page_url": page.url if page else None,
               **{k: item.get(k) for k in ("title", "url", "date", "date_text", "method", "platform") if k in item}}
        with LOCK:
            OUT.write(json.dumps(row, ensure_ascii=False) + "\n"); OUT.flush()


sf.SiteFacts.reject = reject
sf.is_publisher = is_publisher
sys.argv = ["scripts/replay_run.py"] + sys.argv[2:]
runpy.run_path("scripts/replay_run.py", run_name="__main__")
