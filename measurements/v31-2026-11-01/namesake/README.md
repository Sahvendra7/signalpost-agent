# Foreign namesakes (LOGSCOM AS / Logscom AB): impact of the correction on captured bytes

Code `334a085` was compared with `0e4c426` on every captured set: smoke100, midsize40, fresh60, fresh60b, diag80,
eval120, eval200 and eval200b. Together they hold 860 organisations, 411 of them with a verified site.

- Replays were run from the baseline captures (`impact_replays.sh`). The old outputs are the stored `0e4c426`
  replays: `p-anchored-<set>`, or `f2-eval200b` for eval200b.
- `impact_compare.py` lists every published unit (social profile, news item, careers page, job posting, official
  website) and every site-operator decision that differs, with its audit label.
- Result: `impact-vs-0e4c426.txt`.

| Set | Published units removed | Added | Operator changes |
|---|---|---|---|
| eval200 | 2 (`facebook.com/logscom` and `instagram.com/logscom_ab`, both labelled **incorrect**) | 0 | 1 (830872752: `self/no_contrary_signal` → `group_or_brand/site_of_a_foreign_namesake`) |
| eval120 | 0 | 1 (see below) | 0 |
| the other six | 0 | 0 | 0 |

**The eval120 addition is not caused by this change.**
- The unit is 955599535 `fib.no/stottespillere/sparebankstiftelsen-dnb`, dated 2026-11-04.
- That date is the page's application deadline ("Søknadsfrist: 4. november 2026"). On the stored replay (run
  2026-11-02) the deadline was in the future and was rejected. On the day of this comparison (2026-11-04) it is not.
- `0e4c426` replayed eval120 on 2026-11-04 publishes exactly the same 126 units as `334a085`
  (`eval120-0e4c426-same-day.txt`).
- So this is an existing defect that depends on the run date: a deadline read as a publication date. The news rules
  are frozen for this candidate, so it is reported in `docs/v31-release-report.md` rather than fixed.

The two legitimate-profile controls, Kameo NUF and Alpha Solutions Norge, are unchanged. Both are pinned in
`tests/test_v3_regressions.py::SharedNameAcrossBorders`.
