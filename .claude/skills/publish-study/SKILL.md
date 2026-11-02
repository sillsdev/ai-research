---
name: publish-study
description: Publish a research study to the public research site, turning a research harness's results and findings into a study page. Use when asked to publish, write up or draft a study, or to put results on the site.
---

A study is a folder `studies/YYYY-MM-<slug>/` holding `index.qmd` (the write-up), `sources.yml` (where each number came from) and `data/metrics.csv` (generated from `sources.yml`). `studies/2026-10-chrf-b/` is the worked example: read it before writing a new one.

The site is **public**. Every step below serves one rule: a reader sees aggregate results with their uncertainty, traceable to a commit, and nothing that identifies a translation project or quotes draft or copyrighted text.

## 1. Scope the study

Settle with the researcher:

- **Harness**: which research harness produced the results. Load its skill, `harness-<name>`, which holds the anonymization rules. If the results come from no harness, or from a temporary one without a skill, the study is a **one-off**: read [one-off.md](one-off.md) and follow it alongside the steps below.
- **Question and conclusion**: what the study set out to answer, and what the researcher concludes. Take these from the researcher or from their written findings, never from your reading of the numbers alone.
- **Material**: the findings, sections or experiments it covers, and the authors.

Done when you can name the source repository and commit, the exact results files, and the question in one sentence.

## 2. Build the data

Write `sources.yml`, naming each source repository with its `repo` URL, pinned `commit` and `visibility`. The harness skill says which visibility applies. The format is documented in `research_site/importer.py`.

The tables, which map results to metrics, go in one of two places:

- **Public source**: under `tables:` in the study's `sources.yml`.
- **Private source**: in a **recipe** inside the private repository (`recipe:` gives its path), with any `label-files` mapping identifiers to public labels. The recipe names private files and real project codes, so it never enters this repository.

Each table entry picks rows from a results file (or many, with globs) and maps columns to `system` (what is compared), `group` (the test or subset) and one or more measures, with `lower`/`upper` for intervals and `n` for sample size. `melt` turns a wide table (one column per project) into rows. `rename` gives public, readable names and replaces any identifier the harness skill says to anonymize. `aggregate` pools many projects or experiments into statistics; the harness skill says when to use it.

Run `uv run rs-import studies/<slug>`. It reads every source at its pinned commit, never from the working tree. While drafting a recipe, add `--draft-recipe <source>=<path>`. Once the recipe is right, commit it in the private repository, pin that commit in `sources.yml`, and import again without the flag.

The experiment bucket (`bucket: true`) has no commits, so it is pinned by content instead. The recipe sits in the bucket, and `--freeze` copies the files it reads beside it and records a `snapshot`. The harness skill gives the steps.

Done when `data/metrics.csv` holds every number the write-up will cite and nothing it won't, imported from committed sources.

## 3. Write the study

Follow the structure of the example: Summary, the problem, the method, how it was tested, results, limitations, and how to reproduce it. Results are code cells calling `research_site.Study`: `table`, `bar_chart` for measures with a meaningful zero (shares, rates), and `dot_chart` for scores whose axis can't start at zero. A chart cell needs `#| renderings: [light, dark]`. The reproduction section calls `study.provenance()`, which links public sources and describes private ones without linking them.

Write for a reader outside the group who knows machine translation:

- **Every number traces** to `metrics.csv`. A number that comes only from the harness's prose (a findings document, a plan) gets an HTML comment starting `<!-- REVIEW:` that says where it came from. The validator blocks publishing until someone resolves it.
- **Uncertainty is stated.** Give intervals and sample sizes, and say when a difference is within noise.
- **Self-contained.** Leave out internal shorthand: section and finding numbers, script names, team jargon. The harness skill lists the translations it needs.
- **Anonymized** by the harness skill's rules.

Front matter needs `title`, `description`, `date`, `author`, `harness` and `categories`. `allowed-terms` lists any country or place names that are safe to publish, such as a Biblical place or a public dataset's language.

## 4. Check it

1. Run the harness skill's anonymization pass. For a private harness, it includes an **identifier check**: a command that reads the real project codes and other identifiers from the private data itself and searches the study for them, so no list needs keeping and no identifier is written into this repository. A private harness skill without an identifier check gets one before anything is published from it.
2. Run `uv run rs-validate studies/<slug>`. It passes once the REVIEW notes are resolved. Until then, the REVIEW notes should be its only errors.
3. Run `uv run quarto render studies/<slug>/index.qmd` and open `_site/studies/<slug>/index.html`. Check that tables and charts render, labels don't collide, and the prose numbers match the tables.

Done when the page renders cleanly and every remaining validator error is a REVIEW note you will raise.

## 5. Hand off

Report to the researcher what the page claims, each REVIEW note, and anything you anonymized or left out. Once they agree, commit to a `study/<slug>` branch and open a pull request listing the REVIEW notes. The PR is where a second person reviews it before it goes public.
