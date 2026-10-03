# Crawl safety and personal data

## Outbound requests (company websites)

| Control | Implementation |
| --- | --- |
| Public addresses only | `website.assert_public_url`. It allows `http`/`https` only and rejects `localhost` and `*.local`. Every resolved address must be globally routable (private, loopback, link-local, CGNAT, multicast and reserved addresses are blocked). It is checked per origin before any request. |
| Restricted platforms | LinkedIn, Facebook/Meta (incl. `fb.com`, `fb.me`), Instagram, Threads, YouTube (`youtu.be`), X/Twitter (`t.co`) and TikTok are refused by `assert_public_url` before any DNS lookup, both as initial URLs and as **redirect targets** (`RESTRICTED_PLATFORM_DOMAINS`). Site research reports these as `blocked_platform_host`. |
| Redirects | `SafeRedirectHandler`. Every redirect target passes the same check, with at most **5** hops (RFC 9309 asks crawlers to follow at least 5) and at most 2 repeats of one URL. |
| robots.txt | It is fetched once per origin per run. The decision logic (`website.robots_policy`, RFC 9309 §2.3.1) is below. |
| Crawl-delay | Applied per origin, between requests to that origin, including after the robots.txt request. Fractional values are parsed, because CPython drops them. A delay that would overrun the company budget, or that exceeds 30 s (half the 60 s company budget), skips the page (`crawl_delay_exceeds_budget`). It is never ignored. In the v1 registry-website module, a Crawl-delay means the homepage is fetched after the delay and the secondary pages are skipped; site research fetches and paces those pages. |
| Timeouts | 15 s per request (site research and the v1 homepage fetch). Brreg JSON uses `http.fetch_json` with its explicit timeout. |
| Retries | Site pages: at most 2 attempts. v1 robots.txt and homepage: 1 attempt. Brreg: at most 3 attempts, with backoff, on transport errors, 5xx and 429 only. There are no unbounded retries. |
| Budget | At most 30 requests and 60 s per company (shrunk near the batch deadline), and 3 MB per page. |

robots.txt decisions:

| robots.txt response | Decision |
| --- | --- |
| 200 | Parse the first 512 kB. |
| 404, 410 and other 4xx | Treated as "unavailable": crawling is allowed. |
| 401, 403 | Disallow. This is more conservative than the RFC and matches CPython's `RobotFileParser.read`. |
| 429, 5xx or a network failure | Treated as "unreachable": complete disallow (`robots_unreachable`). |

Previously, an unreachable robots.txt allowed the v1 homepage fetch, and a 5xx allowed site research. Both
now disallow. The request strategy and the number of pages are otherwise unchanged.

**Found in final validation (2026-10-03).** The live 1,200-company run with a host audit showed requests to
www.facebook.com, www.instagram.com and www.linkedin.com. These were redirects from company pages, which the
earlier redirect guard followed because the targets are public hosts. The page was then discarded
("redirected outside registered domain"), but the request had already been made. Platform hosts are now
refused at every hop, and the final live runs were repeated with the host audit (see
`measurements/final-validation-2026-10-03/`).

The same run lost three verified websites whose robots.txt sets `Crawl-delay: 20`. The first cap was 10 s,
so those sites were skipped. The cap is now 30 s, and a 20 s delay is honoured within the company budget.

**Residual risk.** The address check resolves the host before urllib connects, so DNS rebinding between the
two lookups is not prevented.

Tests: `tests/test_crawl_safety.py`, plus the outbound-policy tests in `tests/test_site_research.py`.

## Personal data

Brreg's roles response includes each person's birth date (`fodselsdato`) and a deceased flag (`erDoed`). No
claim needs either. `privacy.redacting_fetcher` wraps the registry fetcher and removes both keys
recursively from every `/roller` response, before the response is:

- hashed;
- written to `--snapshot-dir`;
- parsed;
- put into a profile, an envelope or the report.

The evidence SHA-256 is computed over the redacted canonical JSON that the snapshot holds, so every hash still
verifies offline. The trade-off is that the original response bytes are not kept. Names and roles are kept,
because they are published in a company context and are the leadership facts.

Tests: `tests/test_privacy.py`. It runs a batch with a fixture birth date and scans every snapshot file, the
envelopes, the profiles and the report for it.
