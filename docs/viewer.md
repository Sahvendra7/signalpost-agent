# Offline results viewer

There are two ways to build the viewer. Both produce one self-contained HTML file.

- At the end of a batch, add `--viewer-output out/viewer.html` to `scripts/run_competition_batch.py`.
- From an existing envelope JSONL (or `.jsonl.gz`), run:

  ```bash
  uv run python scripts/build_viewer.py --envelopes out/envelopes.jsonl --report out/run-report.json --output out/viewer.html
  ```

Open the file in any modern browser. It needs no server, framework or network.

What the page shows:

- **List:** search by name or organisation number. Filter by terminal status or by flag: with errors, with
  changes, verified website, registry only (sparse), or values retained after an outage.
- **Each company:**
  - identity and status;
  - the deterministic summary (`docs/company-summary.md`), with "sources" under every statement;
  - every fact as FACT → SOURCE → DATE (category, field, value, reporting period, source link and
    retrieval date);
  - each source's SHA-256 and claim span;
  - unknowns with their state and reason;
  - changes since the previous run;
  - errors;
  - the state of each source module.
- **Layout:** two panes on desktop. On phones the list and the detail are separate screens, with a back
  button, and the page never scrolls sideways.

Safety and size:

- **Rendering:** data is embedded as JSON with every `<` written as `<`. It is rendered through
  `textContent` only, never `innerHTML`. A Content-Security-Policy of `default-src 'none'` blocks every
  network fetch from the page. Only `http(s)` source URLs become links, and they open with
  `rel="noopener noreferrer"`.
- **Compact projection:** the page uses a compact projection of the envelopes. It has a per-company source
  table, claim values cut to 400 characters and claim spans cut to 160. The envelopes themselves stay the
  record of truth.
- **Measured size:** the 1,200 companies of the live audit run give a 12.8 MB file that loads in about
  1 second in headless Chromium.

Tests: `tests/test_viewer.py`. They cover self-containment, the JSON round trip, hostile text and the CLI
flag, plus a headless-Chromium check at desktop and phone sizes when Node and Playwright are installed.
