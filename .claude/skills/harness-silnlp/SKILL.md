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

A recipe table can match many experiments with a glob in `file`. `capture` turns named groups in each path into columns, such as the experiment folder or the checkpoint in `scores-<checkpoint>.csv`. A study across many languages pools them; see "Pooling many experiments".

## Files by experiment type

Inspect an experiment folder before writing its recipe. A type not listed here gets added to this skill before anything is published from it.

**Translation** (a `config.yml` with `corpus_pairs`, plus `scores-<checkpoint>.csv`):

- `scores-<checkpoint>.csv`, one per tested checkpoint. Its columns are `book, src_iso, trg_iso, num_refs, references, sent_len, scorer, score`. `book` is `ALL` for the whole test set, or a book code when scored by book. Use `name: {column: scorer}` for the measure. `parse: leading-number` reads BLEU, which silnlp writes as the score followed by its n-gram precisions, brevity penalty and lengths.
  Newer runs write a wide `scores-<checkpoint>.csv` instead: one row per test set, a `draft_index` column, and a column per scorer (`BLEU` as a plain number, its details in `BLEU_*` columns, then `chrF3`, `chrF3+`, `chrF3++`, `spBLEU` and others). List each scorer as its own measure, `{column: chrF3}`, with no `parse`. `sent_len` is the number of test verses.
- `config.yml` and `effective-config-*.yml` describe the setup. Describe the settings that differ between experiments (parent model, vocabulary size, data mix) in the study's prose. Don't import these files, because they name projects.
- Choose the checkpoint(s) to report with `where` on the captured checkpoint, and say in the study which one was used (best on validation, or last).

**Alignment** (a `config.yml` with an `aligner`):

- `corpus-stats.csv`: one row per source/target pair, with verse counts, `align_score` and scripts.
- `detailed_percentages_<project>.csv`: percentages by book (rows) and chapter (columns). Use `melt` to turn the chapter columns into rows.

## Pooling many experiments

A study comparing configurations across many languages shows pooled figures (the mean, the range, and the languages where each configuration beats the baseline), with no row per language. Every system to compare goes in **one** table, since pooling only compares systems within a table:

```yaml
  - file:                      # a glob per configuration
      - MT/experiments/<group>/Base.???/scores-*.csv
      - MT/experiments/<group>/AE.???.hmm/scores-*.csv
    capture: '<group>/(?P<config>Base|AE)\.(?P<language>[a-z]{3})(?:\.(?P<aligner>hmm))?/scores-(?P<checkpoint>\d+)\.csv$'
    where: {book: ALL, scorer: [CHRF3, BLEU]}
    latest: {column: checkpoint, per: [config, aligner, language]}
    system: {column: [config, aligner]}   # rejoins a configuration split around the language
    rename: {Base: Baseline, AE.hmm: Alignment-enhanced}
    group: Whole test set
    measures:
      - {column: score, name: {column: scorer}, parse: leading-number}
    aggregate:
      across: languages
      by: language
      paired: true
      baseline: Baseline         # its published name, after rename
      stats: [mean, min, max, wins]
```

- **One checkpoint per experiment.** Most experiments have two score files, and their names don't say which checkpoint was best. `latest` keeps the last one; say so in the study. To report the best instead, list each experiment's best checkpoint in the recipe with `where`. With neither, the import stops, because two rows for one language would count it twice.
- **The same languages for every system.** `paired` drops languages missing a system or a score. Older runs sometimes lack chrF3, so the pool can differ by measure. rs-import prints how many it left out; give the count in the study ("6 of the 8 languages had all four configurations").
- **Head-to-head counts.** `wins` gives each system's wins over the baseline, with n the languages compared, for claims like "better in 5 of 6 languages". Ties don't count as wins. Error rates (WER, TER) go in their own table with `better: lower`.
- **Pool, or show languages.** Pool unless the study's point depends on individual languages, such as a pattern by language family. Then show labelled rows instead, knowing each label is added to `labels.yml` for good.

**Off limits, in every type**: `*.txt` text and predictions, `*.vref.txt`, vocabularies and models, `.xlsx` workbooks, and the large per-pair CSVs (`<src>_<trg>_<date>.csv`). These hold verse text or per-verse rows.

## Anonymization pass

Experiment paths and files are full of identifying names: country and language folders (`<Country>/<Language>/...`), Paratext project codes with dates (`<iso>-<ProjectName>_<yyyy>_<mm>_<dd>`), ISO codes, and the `references` column of a scores file.

1. **Run the identifier check**, after freezing: `uv run rs-check-bucket studies/<slug>`. It reads the identifiers from the bucket each time: every project code in `MT/scripture`, and, for the study's own experiments, their folder names, ISO codes and the projects in their scores and configs, plus every key of the label files. It prints each line of the study that names one, with the identifier, and exits 0 only when there are none. Replace each hit with its label or leave it out. List a term under `allowed-terms` only when it is safe to publish, such as a published Bible's name.

   The check reads labels from the label files only, so map a project to its label in `labels.yml`, not in a table's `rename`.
2. **Read the study** for what the check can't see, such as a language or country name in prose that no folder or code spells the same way:
   - Every target or minority language, project, team and country becomes a label from `labels.yml` ("Language A", "Project B"), including ISO codes.
   - A published Bible used as a source may be named as a published Bible (BSB, NIV), and a widely published major language such as English or French may be named. Quote no text from either.
   - Describe experiment groups by what they test, never by their folder name.
   - Leave out anything that points to one project without naming it, such as a script, region or corpus size.

Done when `rs-check-bucket` exits 0, and the study's `metrics.csv`, prose and front matter contain no folder name, ISO code or project code, with every label coming from `labels.yml` or the recipe.
