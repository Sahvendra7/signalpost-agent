# C300 revision: same-day live runs (2026-10-17)

Results and method: `docs/c300-revision.md` §F. Nothing here is a Builderr score.

| Directory | Code | What |
| --- | --- | --- |
| `r1-100/` | `05d7566` (Revision 1) | the documented command on the 100-company smoke set |
| `final-100/` | `6487205` (final candidate code) | the same command and input; **`envelopes.viewer.html` is the viewer that command wrote** |
| `final-100-refresh/` | `6487205` | the same, with `--previous-profiles` from `final-100` (profiles not committed): 0 change events |
| `final-911771098/` | `6487205` | HANS JØRGEN SANDNES AS, the C300 WordPress/LinkedIn case, with its viewer |
| `new-100/`, `new-100-refresh/`, `new-911771098/` | `7492f32` (main code commit) | the same three runs, made first |
| `new-929336038-recheck/` | `7492f32` | re-run of SJØLOFTET, whose robots.txt was unreachable during `new-100` |

- **Input:** `measurements/submission-smoke-2026-10-03/input-companies.jsonl`; SHA-256 in `inputs.sha256`.
- **Commands:** `run_all.sh` (Revision 1 and `7492f32`) and `run_final.sh` (`6487205`). Both use
  `measurements/final-validation-2026-10-03/host_audit.py`. Settings: the documented command without a viewer flag,
  8 workers, no `--bulk`, snapshots on.
- **Analysis:** `analyse.py` wrote `analysis.json`. It covers contract validation with every snapshot hash
  re-verified, the summary checker, hosts contacted, the viewer, and the difference in site facts between Revision 1
  and `final-100`. `cross-version-refresh.json` is the offline refresh from Revision 1's profiles to each new run,
  computed with `6487205`.
- **Not committed:** profiles, snapshots and host lists. The `viewer.path` values in the reports point to the
  machine the runs were made on.
