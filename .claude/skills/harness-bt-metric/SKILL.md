---
name: harness-bt-metric
description: Where bt-metric's results and findings are, what can be published from them, and how to anonymize them. Use when publishing or citing results from bt-metric, the research harness for chrF-B and other translation quality metrics.
---

bt-metric (https://github.com/sillsdev/bt-metric, checkout at `../bt-metric`) is research toward a quality metric for comparing MT systems on held-out Bible books; its main result so far is chrF-B.

## Where things are

Read at a commit, never from the working tree: `git -C ../bt-metric fetch`, then pin `origin/main`'s hash in `sources.yml`. The local checkout may be behind or carry uncommitted changes.

The repository is being prepared for public release, and its `results/` hold nothing to anonymize, so studies cite it as `visibility: public` with their tables in `sources.yml`. The validator confirms this against GitHub, and it fails until the repository is actually public.

- **Findings**: `PLAN.md`. The research plan doubles as the findings record: each section's "status" or "first results" paragraphs, with tables, are the findings. The chrF-B definition and its evidence are in section 4.1.1, significance thresholds in section 5, cross-language normalization in section 2.4.
- **Results**: `results/*.tsv`, the summary tables behind PLAN.md's figures. Every file here is aggregate and may be published. The README names the command that writes each one.
- **Off limits**: `data/`, which is gitignored and local. It holds per-verse rows, scored text and the field-test workbooks. Nothing from it goes into a study.

Some PLAN.md figures have no results file (for example the capped significance bands in section 5). Cite them with a REVIEW note and tell the researcher, so the harness can save them.

## The evidence, in public terms

PLAN.md's tests, with the names a study should use:

| PLAN.md | Results files | In a study |
|---|---|---|
| Field tests (section 3.3g) | `field_test_*.tsv`, `combination_field_tests*.tsv` | Translation teams' judgments of drafts in the 2025 Scripture Forge field tests. Explain "independent references" (texts that existed before the trial), since many references were edited from a draft |
| Challenge set (section 3.3a) | `challenge_set*.tsv`, `natural_errors*.tsv` | Synthetic errors injected into real MT outputs; natural errors are real decoder loops, copies and over- or under-long outputs |
| Silver labels (section 3.3c) | `silver_agreement.tsv`, `significance_thresholds_bible.tsv` | xCOMET-XL's preferences on past systems' outputs in languages it supports |
| Human-translation test (section 3.3b) | `human_translations*_summary.tsv` | Published English Bibles scored against the NASB alongside MT systems. Leave out `en-NASB1995`, which is effectively the reference |
| WMT meta-evaluation (sections 3.1, 3.5) | `meta_eval*.tsv`, `mqm_error_categories*.tsv`, `wmt_human_references.tsv`, `significance_thresholds.tsv` | Public human judgments of news translation (WMT MQM and DA, AfriMTE) |

Feature names in the results (`coverage-target`, `key-terms`, `bt-nllb`, `*-detector`) need a plain description on first use. The README's feature table defines each one.

## Anonymization pass

The public PLAN.md and `results/` were already scrubbed of team names, countries, trial names and project codes. The pass keeps a study that way:

- Field-test teams, trials and projects appear only as counts ("5 comparisons", "18 teams"), never by name, language, country or project code, even if the researcher mentions them.
- Published Bible names and WMT, AfriMTE and language-pair names are public and may appear.
- Quote no verse text. Describe the errors and examples in words.

Done when every proper noun in `index.qmd` and `sources.yml` is a public dataset, a published Bible, a tool or an author.
