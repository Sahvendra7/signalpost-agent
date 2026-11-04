# INVALID — do not use these results

Every news run on the diagnostic sets eval200 and eval200b made before commit "fix aid excerpt alignment" used packets
whose `source_text` was the label-aid excerpt of a *different* unit: `datasets.labelled_news_items` numbered rows of
items.labelled.csv including `official_website` rows, while aid.md numbers only the labelled units (it skips websites).
Measured impact: the unit's own title occurred in its source text for 8/269 (eval200b) and 17/175 (eval200) packets,
against 199/352 and 94/211 after the fix. Article text (fetched separately) was correct where captured.

Consequences: the pilot, the dev runs, the dev80 prompt/model grid and the eval200b diagnostic are invalid, including
every precision/coverage figure computed from them and the prompt-selection evidence. They are kept only as a record.
Unaffected: evalg250 (packets built from the captured snapshots), social, synthesis and What's New experiments.
Regression test: tests/test_llm_gemini_experiment.py::test_aid_excerpts_are_matched_to_their_own_unit.
