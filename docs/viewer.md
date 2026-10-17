# Offline results viewer

Every documented run writes one self-contained HTML file next to its envelopes. Nothing extra is needed:

```bash
uv run python scripts/run_competition_batch.py --organisations <BATCH.jsonl> --output out/envelopes.jsonl \
  --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <RUN_ID>
# -> out/envelopes.viewer.html  (path also in out/report.json "viewer" and in the printed summary)
```

- The default path is `--output` with its extension replaced by `.viewer.html`. Use `--viewer-output PATH` to choose
  another path, or `--no-viewer` to skip it.
- The viewer is written after the envelopes, profiles and report are durable. If it fails, the run still exits as
  before, and `report.viewer.reason` says why.
- An existing envelope JSONL (or `.jsonl.gz`) can be turned into a viewer too:

  ```bash
  uv run python scripts/build_viewer.py --envelopes out/envelopes.jsonl --report out/report.json --output out/viewer.html
  ```

Open the file in any modern browser. It needs no server, framework or network. A viewer of the live 100-company smoke run
is committed: `measurements/c300-revision-2026-10-17/final-100/envelopes.viewer.html`.

What the page shows:

- **List:** search by name or organisation number. Filter by terminal status or by flag: verified website, profiles
  or dated activity, with changes, source failures, with errors, registry only (sparse), or values retained after an
  outage. Sort by input order, name, most recent revenue or number of facts. Arrow keys move through the list.
- **Each company:**
  - previous / next navigation through the filtered list, and a link of its own (`#org=<organisation number>`);
  - the deterministic summary (`docs/company-summary.md`), starting with "At a glance", with "sources" under every
    statement (source URL, source class, retrieval date, SHA-256 and claim span);
  - every fact as FACT → SOURCE → DATE, grouped by area: identity and description, financials (with reporting
    period and currency), leadership, locations, website and public activity;
  - unknowns with their state and reason, changes since the previous run, errors, and the state of each source
    module (failed and blocked sources are marked).
- **Compare:** tick up to four companies and press Compare. The comparison is a table of key fields, one column per
  company: legal form, status, founding date, address, industry, employees, most recent accounts period, revenue,
  operating result, net result, equity, chief executive, board chair, website, profiles, dated website items, job
  postings, and what is unknown. Every value links to its source, with its retrieval date. A missing value says why
  (for example "unknown (not published; not zero)"). The comparison has its own link (`#compare=<org>,<org>`).
- **Layout:** two panes on desktop. On phones the list and the detail are separate screens with a back button. Wide
  tables scroll inside their own box, so the page never scrolls sideways.

Safety and size:

- **Rendering:** data is embedded as JSON with every `<` written as `<`. It is rendered through `textContent`
  only, never `innerHTML`. A Content-Security-Policy of `default-src 'none'` blocks every network fetch from the page.
  Only `http(s)` source URLs become links, and they open with `rel="noopener noreferrer"`.
- **Compact projection:** the page uses a compact projection of the envelopes. It has a per-company source table,
  claim values cut to 400 characters and claim spans cut to 160. The comparison cells are computed in Python
  (`viewer._compare_cells`) with the same most-recent-period selection as the summary. The envelopes themselves stay
  the record of truth.
- **Measured size:** about 14 KB per company (1.38 MB for 100 companies, 16.2 MB for 1,200). In headless Chromium
  the 1,200-company page loads in 1.2 s (desktop) and 1.5 s (phone viewport); a search takes 0.1–0.25 s.

Tests: `tests/test_viewer.py` and `tests/test_c300.py` (`ViewerExposure`). They cover self-containment, the JSON round
trip, hostile text, the default viewer on the documented command, `--no-viewer`, the comparison cells, and two
headless-Chromium checks at desktop and phone sizes when Node and Playwright are installed: open a company, its
sources, search, deep link, compare and sort, with no page error, no network request and no horizontal page scroll.
