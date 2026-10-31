# Research site

Everything in this repository is published to a **public** website. Treat every file as public the moment it is written.

- To create or change a study, use the `publish-study` skill, which loads the harness's skill. The harness skill sets what can be published and how to anonymize it.
- Copy summaries only, through `sources.yml` and `rs-import`. Raw results, per-verse rows, model outputs and corpus text stay in the harness.
- Every number in a study traces to its `data/metrics.csv`, or carries a `<!-- REVIEW: -->` note saying where it came from.
