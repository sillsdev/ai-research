---
name: harness-bt-checking-eval
description: Where bt-checking-eval's results and findings are, what can be published from them, and how to anonymize them. Use when publishing or citing results of bt-checking-eval, the harness for LLM-based checking of Bible translation drafts.
---

bt-checking-eval (https://github.com/sillsdev/bt-checking-eval, checkout at `../bt-checking-eval`) runs an LLM "translation consultant" over drafts seeded with known errors and scores how many it catches. The code repository holds no data. The corpus, results and findings are in **bt-checking-eval-data** (https://github.com/sillsdev/bt-checking-eval-data, checkout at `../bt-checking-eval-data`), which is private and stays private.

## Before the first public study

`bt-checking-eval-data/PROVENANCE.md` is the policy for everything in that repository. Read its "Raw text and derived work" section. Its audience table must have a **public** tier for pooled, anonymized results before anything from this harness is published. If the table still tops out at "internal SIL collaborators", stop and tell the researcher: the policy changes first, in its own pull request.

## Source and recipe

The study's source is the data repository, as a private git source:

```yaml
sources:
  bt-checking-eval-data:
    repo: https://github.com/sillsdev/bt-checking-eval-data
    commit: <commit holding the recipe>
    visibility: private
    recipe: published/<slug>.yml
```

The recipe and the register entry (see the end of this skill) go into the data repository together. Follow that repository's `CLAUDE.md` working rules: a branch, and a pull request opened as a draft. Draft the recipe with `--draft-recipe`. Pin the commit after it merges.

## Where things are

- **Findings**: `FINDINGS.md` (numbered F1, F2, …) and `FINDINGS_PTA.md` (P-numbered, the Paratext Assistant configurations). Methodology is in `MEASUREMENT.md` and `MEASUREMENT_PTA.md`. The opening sections of FINDINGS.md define the measures and the noise floor.
- **Score matrices**: `projects/*.tsv`, one row per run (a checker configuration, which the findings call an "arm"), one column per project, and an `overall` column that is the verse-weighted mean over the eleven projects.
  - Metric files: `precision`, `recall`, `f1`, `f2`, and `clean_fa_rate` / `clean_fa_share` (false alarms on verses with no seeded error). Prefixed variants restrict to an error category (`accuracy_`, `terminology_`, `linguistic-conventions_`) or change the unit (`defectlevel_`, `verselevel_`).
  - `cost.tsv`, `tokens.tsv` and `seconds.tsv` are per chapter per run, with no project columns.
  - `discourse.tsv` is long, with a `project` column. `fn_phenomena.tsv` gives missed errors by phenomenon.
  - The row `verses` gives project sizes, which identify projects. Never import it.
- **Reference cohort**: `cohorts/reference/*.tsv`, the same matrices for checking runs on published, openly licensed Bibles rather than drafts.
- **Off limits**: everything under `projects/<code>/`. `issues*.json`, `test.json`, `src.txt`, `trg.txt`, `bt/` and `aqua/` quote verse text, and per-verse or per-defect listings can't be de-identified.

## What a study may show

Results are pooled or shown as distributions, never per project:

- **Pooled**: the `overall` column, selected with `melt` and `where: {project: overall}`.
- **Across projects**: the eleven project columns with `aggregate: {across: projects, stats: [min, median, max]}`, or counts ("better in 8 of the 11 projects") stated in prose.
- **No per-project rows, even under labels.** A stable "Project A" through "Project K" is still a disclosure, as `check_provenance.py` warns, so this harness has no label file.
- **Noise.** Compare differences with the noise floor in FINDINGS.md, which depends on the configuration. Treat a difference below it as a tie, and say which floor applies.

Name configurations by what they do ("plain prompt", "with AQuA critique"), not by run IDs.

## Anonymization pass

1. Mark the study's files as tracked (`git add -N studies/<slug>`), then run from this repository:

   ```
   uv run --project ../bt-checking-eval python ../bt-checking-eval/check_provenance.py --data-dir ../bt-checking-eval-data
   ```

   It checks every tracked file here for corpus phrases and for project codes, including the reference cohort's `ref-` codes. It must exit 0.
2. Read the study for what the check can't see: language and draft names (PROVENANCE.md's project table lists them), countries, scripts or regions that point to one project, project sizes, and verse text of any kind. Refer to reference-cohort Bibles by their published names.

Done when the check exits 0 and the study names no language, project, draft, place or script tied to a project.

## Register the publication

PROVENANCE.md's "Published documents" table records every broadly shared document built from this data. Add a row for the study in the same data-repository pull request as its recipe:

- the study's title;
- its source: the recipe path;
- its audience: public;
- whether it holds raw text: no.

Add its URL to "Where each of these is published" once the site is live.
