# One-off studies

A study whose results come from no harness, or from a temporary one with no `harness-*` skill. With no harness skill to set the rules, the defaults below apply, and the study keeps its own copy of the results summaries.

If the same harness will produce a second study, write its `harness-<name>` skill instead, following the existing ones.

## Ask the researcher first

Get answers to all four before copying anything:

1. **Origin.** Who produced the results, with what code, and when. This becomes the source's `origin`, so phrase it for a public reader.
2. **Whose data.** Do the results come from translation teams' drafts, partners' data or licensed text? Does any agreement limit publishing them? If nobody knows, stop until someone does.
3. **What could identify a project.** Which languages, projects, teams, places and project codes the results involve. Keep this list in the conversation, never in the repository. You'll search for each item later.
4. **Which files.** The summary tables the write-up needs, not the raw outputs.

Done when you can write the `origin` sentence and list every identifier to search for.

## Default rules

- **Summaries only.** Leave out verse text, model outputs, and per-verse or per-segment rows.
- **Name no project.** Minority languages, projects, teams, countries and regions, scripts tied to a project, ISO codes, Paratext project codes and folder names all become labels ("Language A") or are left out.
- **What may be named.** Published Bibles, widely published major languages such as English or French, and public datasets. List any country these need under `allowed-terms`.

## Build the data

1. Copy the summary tables into `studies/<slug>/source/` as `.csv` or `.tsv`. **Anonymize the copies before they enter the repository**: replace identifiers with labels in the files themselves. A `rename` in `sources.yml` would publish the real names beside their labels. The researcher keeps the label mapping outside this repository.
2. Declare the source and list its tables, with `file` relative to `source/`:

   ```yaml
   sources:
     results:
       in-study: true
       origin: Computed by <who> with <what>, <month year>

   tables:
     - source: results
       file: scores.tsv
       system: {column: model}
       measures:
         - {column: chrF3}
   ```

3. Set `harness: none` in the front matter.

`study.provenance()` turns the `origin` into the reproduction section and links each file in `source/`.

## Check

Before step 4 of the main skill, search the whole study folder, case-insensitively, for every identifier from question 3. Done when none is found.

When handing off, put the answer to question 2 in the pull request description, so the reviewer can check it.
