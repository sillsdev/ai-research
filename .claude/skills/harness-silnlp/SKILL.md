---
name: harness-silnlp
description: Where silnlp experiment results are in the experiment bucket, which files can be published, and how to anonymize them. Use when publishing or citing results of silnlp experiments (machine translation, alignment).
---

silnlp (https://github.com/sillsdev/silnlp, checkout at `../silnlp`) writes each experiment to the experiment bucket, under `MT/experiments/<group>/<experiment>/`. The bucket root is `SIL_NLP_DATA_PATH`, or pass `--bucket-root` (often `M:/` on Windows).

## Source and recipe

The bucket is private and has no commits, so a study pins it by content:

```yaml
sources:
  silnlp-bucket:
    bucket: true
    visibility: private
    recipe: MT/published/<slug>/recipe.yml
```

1. Write the recipe at `MT/published/<slug>/recipe.yml` in the bucket, with `label-files: [MT/published/labels.yml]`.
2. Run `uv run rs-import studies/<slug> --freeze`. It copies each file the recipe reads into `MT/published/<slug>/files/` and records the `snapshot` in `sources.yml`.
3. Re-run with `--freeze` whenever the recipe changes. Without the flag, imports read only the frozen copies and fail if anything changed.

`MT/published/labels.yml` is shared by every silnlp study, so a language or project keeps one label everywhere. Add new entries, and leave existing ones as they are: changing or reusing a label would contradict studies already published.

A recipe table can match many experiments with a glob in `file`. `capture` turns named groups in each path into columns, such as the experiment folder or the checkpoint in `scores-<checkpoint>.csv`.

## Files by experiment type

Inspect an experiment folder before writing its recipe. A type not listed here gets added to this skill before anything is published from it.

**Translation** (a `config.yml` with `corpus_pairs`, plus `scores-<checkpoint>.csv`):

- `scores-<checkpoint>.csv`, one per tested checkpoint. Its columns are `book, src_iso, trg_iso, num_refs, references, sent_len, scorer, score`. `book` is `ALL` for the whole test set, or a book code when scored by book. Use `name: {column: scorer}` for the measure. `parse: leading-number` reads BLEU, which silnlp writes as the score followed by its n-gram precisions, brevity penalty and lengths.
- `config.yml` and `effective-config-*.yml` describe the setup. Describe the settings that differ between experiments (parent model, vocabulary size, data mix) in the study's prose. Don't import these files, because they name projects.
- Choose the checkpoint(s) to report with `where` on the captured checkpoint, and say in the study which one was used (best on validation, or last).

**Alignment** (a `config.yml` with an `aligner`):

- `corpus-stats.csv`: one row per source/target pair, with verse counts, `align_score` and scripts.
- `detailed_percentages_<project>.csv`: percentages by book (rows) and chapter (columns). Use `melt` to turn the chapter columns into rows.

**Off limits, in every type**: `*.txt` text and predictions, `*.vref.txt`, vocabularies and models, `.xlsx` workbooks, and the large per-pair CSVs (`<src>_<trg>_<date>.csv`). These hold verse text or per-verse rows.

## Anonymization pass

Experiment paths and files are full of identifying names: country and language folders (`<Country>/<Language>/...`), Paratext project codes with dates (`<iso>-<ProjectName>_<yyyy>_<mm>_<dd>`), ISO codes, and the `references` column of a scores file.

- Every target or minority language, project, team and country becomes a label from `labels.yml` ("Language A", "Project B"), including ISO codes.
- A published Bible used as a source may be named as a published Bible (BSB, NIV), and a widely published major language such as English or French may be named. Quote no text from either.
- Describe experiment groups by what they test, never by their folder name.

Done when the study's `metrics.csv`, prose and front matter contain no folder name, ISO code or project code, and every label comes from `labels.yml` or the recipe.
