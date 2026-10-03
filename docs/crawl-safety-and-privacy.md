# Crawl safety and personal data

## Outbound requests (company websites)

| Control | Implementation |
| --- | --- |
| Public addresses only | `website.assert_public_url`. It allows `http`/`https` only and rejects `localhost` and `*.local`. Every resolved address must be globally routable (private, loopback, link-local, CGNAT, multicast and reserved addresses are blocked). It is checked per origin before any request. |
| Redirects | `SafeRedirectHandler`. Every redirect target passes the same check, with at most **5** hops (RFC 9309 asks crawlers to follow at least 5) and at most 2 repeats of one URL. |
| robots.txt | It is fetched once per origin per run. The decision logic (`website.robots_policy`, RFC 9309 §2.3.1) is below. |
| Crawl-delay | Applied per origin, between requests to that origin, including after the robots.txt request. Fractional values are parsed, because CPython drops them. A delay that would overrun the company budget, or that exceeds 10 s, skips the page (`crawl_delay_exceeds_budget`). It is never ignored. |
| Timeouts | 15 s per request (site research and the v1 homepage fetch). Brreg JSON uses `http.fetch_json` with its explicit timeout. |
| Retries | Site pages: at most 2 attempts. v1 robots.txt and homepage: 1 attempt. Brreg: at most 3 attempts, with backoff, on transport errors, 5xx and 429 only. There are no unbounded retries. |
| Budget | At most 30 requests and 60 s per company (shrunk near the batch deadline), and 3 MB per page. |
| Platforms | LinkedIn, Meta and YouTube pages are never fetched. Only the verified site's own outbound links are recorded. |

robots.txt decisions:

| robots.txt response | Decision |
| --- | --- |
| 200 | Parse the first 512 kB. |
| 404, 410 and other 4xx | Treated as "unavailable": crawling is allowed. |
| 401, 403 | Disallow. This is more conservative than the RFC and matches CPython's `RobotFileParser.read`. |
| 429, 5xx or a network failure | Treated as "unreachable": complete disallow (`robots_unreachable`). |

Previously, an unreachable robots.txt allowed the v1 homepage fetch, and a 5xx allowed site research. Both
now disallow. The request strategy and the number of pages are otherwise unchanged.

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
