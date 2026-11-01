# Signalpost search (local app)

A small web app that runs on your own computer. With it you can:
- search companies by name or organisation number;
- open a company's cited profile;
- compare 2–4 companies;
- see what is new since the previous run;
- research a company that is not in your dataset yet. This takes about a minute and uses free public sources only.

It uses the same research pipeline and viewer as the batch command. It needs no account, no API key and no extra
dependency (Python standard library only). The LLM layer stays off.

## Start it

```bash
uv sync
uv run python scripts/serve.py --data-dir out/app
# Signalpost search: http://127.0.0.1:8765/  (0 imported envelopes; Ctrl+C to stop)
```

Open the printed address in a browser on the same computer. It works on a laptop or a phone-sized window.

Optional flags:

| Flag | What it does |
|---|---|
| `--envelopes out/envelopes.jsonl` | Make a batch run's companies searchable. Repeatable. The file is only read, never changed. `.jsonl.gz` files from the run history also work, for example `out/signalpost-history/<run>/envelopes.jsonl.gz`. |
| `--snapshot-dir out/snapshots` | That run's `--snapshot-dir`. The evidence inspector can then offer the exact bytes that were read. |
| `--bulk brreg-enheter.csv.gz` | Search the registry from the bulk file instead of the registry's search API. Loading takes a moment on the first search. |
| `--audit-results audit/results.json` | Show a manual audit in "How reliable is this?". It comes from `scripts/audit_kit.py score`. |
| `--port 8765` | The port to serve on. |
| `--deadline 120` | The time limit, in seconds, for one on-demand research. |

## Use it

1. **Search.** Type a company name ("tyin alpint") or an organisation number ("983 181 732").
   - **In your dataset** lists companies already researched. Each has *Open profile* and a *Compare* tick box. A
     profile older than 30 days also offers *Re-check*.
   - **In the registry — not researched yet** lists matches from the official registry. Deleted entities are marked
     and cannot be researched.
   - Web addresses, e-mail addresses and paths are refused with "Search by company name or organisation number". The
     app never fetches an address you type.
2. **Research this company.** The card shows the current stage, for example "Reading the company's website — 23 s",
   and a *Cancel* button. At most two companies are researched at once; others wait in a queue of up to 20. When
   research finishes, the card shows one of:
   - **Profile ready** — *Open profile*.
   - **Profile ready — some sources could not be checked**, followed by the sources that failed, *Open profile* and
     *Try again*. Failed sources are marked as failed in the profile; nothing is made up.
   - **Research failed**, with the reason: not in the registry, registry unreachable, or cancelled. Nothing is saved.
3. **Profile.** This is the batch viewer for that company:
   - every fact has *Inspect* (source, retrieval time, content hash, quoted span and why the fact is attributed);
   - held-back items appear under "Seen but not attributed";
   - unknowns appear under "Not known".

   *← Search* returns to the search page.
4. **Compare.** Tick 2–4 companies, then *Compare*. On a phone the comparison is one card per field.
5. **What's new.** Lists items that are new since each company's previous run, and items our checks withdrew.

A re-check compares with the company's latest stored run, so new and withdrawn items show up there.

## Where data is kept

`--data-dir`:
- `research/<organisation number>/<run id>/envelope.json` and `profile.json`;
- `snapshots/`, the bytes read during on-demand research.

Directories are created with mode 0700 and files with mode 0600. A run is complete once its `envelope.json` exists;
it is written last, through a temporary file and a rename. Delete the directory to forget everything.

## Security

The app is meant for one person on one computer:

| Concern | What the app does |
|---|---|
| Network exposure | Listens on `127.0.0.1` only. Another `--host` needs `--allow-remote` and prints a warning. |
| DNS rebinding | Any request whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>` gets `421`. |
| Cross-site requests | Starting or cancelling research needs a per-process token from the page, the app's own `Origin`, `Sec-Fetch-Site: same-origin` (or none), and a JSON body of at most 4 KB. |
| Fetching arbitrary addresses | Inputs are names and organisation numbers only. Registry search uses one fixed registry endpoint. Research uses the registry record and the existing website discovery, with its public-host checks. |
| Captured pages | Captured pages are never rendered. They are downloaded as `text/plain` attachments with `Content-Security-Policy: sandbox`, and only for hashes that appear in indexed evidence. Pages insert text with `textContent` only. The search page's policy allows only its own script and style, by hash. |
| Overload | Requests time out after 10 s. At most 32 requests are handled at once (otherwise `503`). Search is limited to 30 per minute and research to 10 per minute (otherwise `429`). |
| Abandoned research | A research thread still finishing after a cancel or deadline keeps its slot until it ends, or for at most 5 minutes. |
| Errors | Responses carry a short message and a code, never a traceback. The log records the method, the path (with the query cut to 20 characters) and the status. |
| Commands | The app runs no subprocess and never passes request data to a shell. |

## Limits

- The registry search API returns at most 20 matches. Make the name more specific, or use the organisation number.
- On-demand research has the batch pipeline's precision rules and limits, described in `docs/v3-accuracy.md`.
- There are no user accounts. Do not expose the app to a network.
