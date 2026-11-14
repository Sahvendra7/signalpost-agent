# Signalpost — instructions for Claude sessions

Read `docs/PROJECT_MEMORY.md` before doing anything. It holds the owner's standing rules, the current state (the V3.1.1
Builderr rescoring revision on branch `revision/v3.1.1-builderr-rescore`, release `9d99cba`, code `38ff24c`), results,
open items and repo gotchas.

The most important rules:
* Never modify the V3.1 release branch `claude/awesome-sagan-m2lppu`, the evaluated commit `ff3b515` or existing tags.
* Never merge, push or submit to Builderr without an explicit instruction in the current session.
* Default execution stays deterministic: no LLM, no paid API, $0, no social-platform fetching. Gemini stays disabled
  and out of the release path.
* Never print or commit an API key.
* Never call a score on a set you tuned on independent; never claim a Builderr score or the 95% threshold from local tests.

Also follow `AGENTS.md`.
