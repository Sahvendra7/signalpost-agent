# Signalpost — instructions for Claude sessions

Read `docs/PROJECT_MEMORY.md` before doing anything — start with its §000 (V3.1.2 final optimization, local branch
`final/v3.1.2-optimization`, code `95a5464`, not pushed or submitted; report `docs/v312-final-optimization.md`) and then §00 (final review done 2026-11-14; proposed
Builderr submission commit `408f41523e9b7aa2ffc45c12656403f9949bcb2b`; corrected email in
`docs/v311-builderr-rescore-email.md`, sent by the owner only). It holds the owner's standing rules, the current state (the V3.1.1
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
