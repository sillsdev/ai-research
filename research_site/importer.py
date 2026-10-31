"""Build a study's data/metrics.csv from the harness result files its sources.yml names.

Usage:
    uv run rs-import studies/<study>
    uv run rs-import studies/<study> --checkout bt-metric=D:/repos/bt-metric
    uv run rs-import studies/<study> --draft-recipe bt-checking-eval-data=PATH
    uv run rs-import studies/<study> --freeze [--bucket-root M:/]

A git source is read at its pinned commit with `git show`, never from the working tree, so
uncommitted or newer results can't leak into a study. Its checkout defaults to a sibling of
this repository named after the source.

A public source lists its tables in the study's sources.yml. A private source lists them in a
*recipe*, a file kept with the private data, because the recipe names private files and maps
real project codes to public labels: published, it would undo the anonymization. `--draft-recipe`
reads a git recipe that isn't committed yet, to try it out before committing it and pinning that commit.

A table can pool many experiments or projects:

- `file` may be a list of glob patterns, and `capture` turns named groups in each path into columns.
  `system: {column: [config, aligner]}` joins several columns with dots, skipping empty ones.
- `latest: {column: checkpoint, per: [config, language]}` keeps each experiment's highest checkpoint.
- `aggregate` collapses rows into statistics, so no row stands for one project or language:
  `{across: languages, by: language, paired: true, baseline: Baseline, stats: [mean, min, max, wins]}`.
  `by` names the column identifying each language and rejects any that has two rows for one system.
  `paired` keeps only the languages every system has. `wins` counts the languages where each system beats
  `baseline` (its published name; `better: lower` for error rates), with n the languages compared.

A bucket source (`bucket: true`) reads the experiment store at SIL_NLP_DATA_PATH (or --bucket-root).
The bucket has no commits, so a study pins it by content instead. `--freeze` copies every file the
recipe reads into a `files/` folder beside the recipe and records a `snapshot` hash of the recipe and
those copies in sources.yml. Later imports read only the copies and fail if the hash no longer
matches, so re-running or moving an experiment can't change a published study.

A one-off study, with no harness or a temporary one, keeps its own summary files in a `source/`
folder beside index.qmd (`in-study: true`, with an `origin` saying where they came from). Its
tables are listed in sources.yml like a public source's, and `file` is relative to `source/`.
"""

import argparse
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pandas as pd
import yaml

METRICS_COLUMNS = ["system", "group", "measure", "value", "lower", "upper", "n", "source", "file"]


class SourceError(Exception):
    pass


class GitSource:
    def __init__(self, source_id: str, spec: dict, checkout: Path):
        self.id = source_id
        self.is_public = spec.get("visibility") == "public"
        self.recipe = spec.get("recipe")
        self._commit = spec["commit"]
        self._checkout = checkout

    def check(self) -> None:
        if not (self._checkout / ".git").exists():
            raise SourceError(f"source '{self.id}': no git checkout at {self._checkout}; pass --checkout {self.id}=PATH")
        try:
            self._git("cat-file", "-e", f"{self._commit}^{{commit}}")
        except SourceError:
            raise SourceError(
                f"source '{self.id}': commit {self._commit} is not in {self._checkout}; run git fetch there"
            ) from None

    def resolve(self, pattern: str) -> list[str]:
        if any(c in pattern for c in "*?["):
            raise SourceError(f"source '{self.id}': {pattern}: patterns are only supported for bucket sources")
        return [pattern]

    def read_recipe(self) -> str:
        return self.read_text(self.recipe)

    def read_text(self, path: str) -> str:
        return self._git("show", f"{self._commit}:{path}")

    def read_worktree_text(self, path: str) -> str:
        return (self._checkout / path).read_text(encoding="utf-8")

    def read_table(self, file: str) -> pd.DataFrame:
        return pd.read_csv(io.StringIO(self.read_text(file)), sep="\t" if file.endswith(".tsv") else ",")

    def finish(self, sources_file: Path) -> None:
        pass

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self._checkout), *args], capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            raise SourceError(f"source '{self.id}': {result.stderr.strip()}")
        return result.stdout


class BucketSource:
    """The experiment store, pinned by a snapshot of frozen copies instead of a commit."""

    is_public = False

    def __init__(self, source_id: str, spec: dict, root: Path | None, freeze: bool):
        self.id = source_id
        self.recipe = spec.get("recipe", "")
        if root is None:
            raise SourceError(f"source '{source_id}': set SIL_NLP_DATA_PATH or pass --bucket-root")
        # The recipe's folder holds the frozen copies, which --freeze replaces; requiring it under a
        # `published` folder keeps that from ever pointing at experiment data.
        recipe_dir = PurePosixPath(self.recipe).parent
        if "published" not in recipe_dir.parts[:-1]:
            raise SourceError(f"source '{source_id}': the recipe must be in its own folder under a 'published' folder")
        self._root = root
        self._files_dir = recipe_dir / "files"
        self._freeze = freeze
        self._snapshot = spec.get("snapshot")
        self._read: dict[str, bytes] = {}

    def check(self) -> None:
        if not (self._root / self.recipe).is_file():
            raise SourceError(f"source '{self.id}': no recipe at {self._root / self.recipe}")
        if self._freeze:
            shutil.rmtree(self._root / self._files_dir, ignore_errors=True)
        elif not (self._root / self._files_dir).is_dir():
            raise SourceError(f"source '{self.id}': nothing frozen yet; run with --freeze")

    def resolve(self, pattern: str) -> list[str]:
        base = self._root if self._freeze else self._root / self._files_dir
        paths = sorted(p.relative_to(base).as_posix() for p in base.glob(pattern) if p.is_file())
        if not paths:
            raise SourceError(f"source '{self.id}': no files match {pattern}")
        return paths

    def read_recipe(self) -> str:
        data = (self._root / self.recipe).read_bytes()
        self._read[self.recipe] = data
        return data.decode("utf-8")

    def read_text(self, path: str) -> str:
        return self._read_bytes(path).decode("utf-8")

    def read_worktree_text(self, path: str) -> str:
        return self.read_text(path)

    def read_table(self, file: str) -> pd.DataFrame:
        return pd.read_csv(io.BytesIO(self._read_bytes(file)), sep="\t" if file.endswith(".tsv") else ",")

    def finish(self, sources_file: Path) -> None:
        snapshot = self._digest()
        if self._freeze:
            write_snapshot(sources_file, self.id, snapshot)
            print(f"froze {len(self._read) - 1} files for '{self.id}'; snapshot {snapshot}")
        elif snapshot != self._snapshot:
            raise SourceError(
                f"source '{self.id}': the recipe or its frozen files changed since the snapshot in sources.yml. "
                "Re-run with --freeze if the change is intended."
            )

    def _read_bytes(self, path: str) -> bytes:
        if self._freeze:
            data = (self._root / path).read_bytes()
            copy = self._root / self._files_dir / path
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(data)
        else:
            frozen = self._root / self._files_dir / path
            if not frozen.is_file():
                raise SourceError(f"source '{self.id}': {path} isn't frozen; run with --freeze")
            data = frozen.read_bytes()
        self._read[path] = data
        return data

    def _digest(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self._read):
            digest.update(path.encode("utf-8") + b"\0" + hashlib.sha256(self._read[path]).digest())
        return f"sha256:{digest.hexdigest()}"


class StudySource:
    """Summary files kept in the study's own `source/` folder (`in-study: true`), for a one-off study.

    There is no harness repository to pin, or it is temporary and may be deleted, so the files are
    copied in, already anonymized, and this repository's history pins them.
    """

    is_public = True
    recipe = None

    def __init__(self, source_id: str, study_dir: Path):
        self.id = source_id
        self._dir = study_dir / "source"

    def check(self) -> None:
        if not self._dir.is_dir():
            raise SourceError(f"source '{self.id}': no source/ folder in the study")

    def resolve(self, pattern: str) -> list[str]:
        paths = sorted(p.relative_to(self._dir).as_posix() for p in self._dir.glob(pattern) if p.is_file())
        if not paths:
            raise SourceError(f"source '{self.id}': no files in source/ match {pattern}")
        return paths

    def read_text(self, path: str) -> str:
        return (self._dir / path).read_text(encoding="utf-8")

    def read_table(self, file: str) -> pd.DataFrame:
        return pd.read_csv(self._dir / file, sep="\t" if file.endswith(".tsv") else ",")

    def finish(self, sources_file: Path) -> None:
        pass


def write_snapshot(sources_file: Path, source_id: str, snapshot: str) -> None:
    """Set the source's `snapshot:` line in place, keeping the rest of the file as written."""
    text = sources_file.read_text(encoding="utf-8")
    block = re.search(rf"^  {re.escape(source_id)}:\n((?:    .*\n?)*)", text, re.MULTILINE)
    if block is None:
        raise SourceError(f"sources.yml: can't find source '{source_id}' to record its snapshot")
    body = block.group(1)
    line = f"    snapshot: {snapshot}\n"
    if re.search(r"^    snapshot:", body, re.MULTILINE):
        body = re.sub(r"^    snapshot:.*\n?", line, body, flags=re.MULTILINE)
    else:
        body = body.rstrip("\n") + "\n" + line
    sources_file.write_text(text[: block.start(1)] + body + text[block.end(1) :], encoding="utf-8")


class TableSpec:
    """One `tables:` entry: which rows of a result file to keep and how its columns map to metrics."""

    def __init__(self, spec: dict, source):
        self._spec = spec
        self._source = source
        # A list of patterns lets one table hold experiments whose folders are named differently,
        # so they can be compared with each other.
        self._patterns = spec["file"] if isinstance(spec["file"], list) else [spec["file"]]
        self.file = ", ".join(self._patterns)
        more = len(self._patterns) - 1
        self._label = self._patterns[0] + (f" (and {more} more)" if more else "")

    def extract(self) -> pd.DataFrame:
        table = self._latest(self._filter(self._melt(self._read())))
        rename = self._spec.get("rename", {})
        unit = self._spec.get("aggregate", {}).get("by")
        if unit is not None and unit not in table.columns:
            raise SourceError(f"{self._label}: aggregate by '{unit}', which isn't a column")
        rows = []
        for measure in self._spec["measures"]:
            missing = [c for c in self._measure_columns(measure) if c not in table.columns]
            if missing:
                raise SourceError(f"{self._label}: no column {', '.join(missing)}")
            for _, row in table.iterrows():
                rows.append(
                    {
                        "_unit": None if unit is None else str(row[unit]),
                        "system": rename.get(v := self._resolve(self._spec["system"], row), v),
                        "group": rename.get(v := self._resolve(self._spec.get("group", ""), row), v),
                        "measure": self._resolve(measure.get("name", measure["column"]), row),
                        "value": self._parse(row[measure["column"]], measure.get("parse")),
                        "lower": row[measure["lower"]] if "lower" in measure else None,
                        "upper": row[measure["upper"]] if "upper" in measure else None,
                        "n": row[measure["n"]] if "n" in measure else None,
                        "source": self._source.id,
                        # A private source's file paths stay private, like the recipe that names them.
                        "file": self.file if self._source.is_public else None,
                    }
                )
        metrics = pd.DataFrame(rows, columns=["_unit", *METRICS_COLUMNS])
        return self._aggregate(metrics).reindex(columns=METRICS_COLUMNS)

    def _aggregate(self, metrics: pd.DataFrame) -> pd.DataFrame:
        """Collapse rows that share a system, group and measure into summary statistics.

        For results shown only as a distribution: with the project or language left out of `system`
        and `group`, each one is a row, and only the statistics survive. `by` names the column that
        identifies them, which `paired` and the `wins` statistic need to match systems up.
        """
        aggregate = self._spec.get("aggregate")
        if aggregate is None:
            return metrics
        across = aggregate["across"]
        keys = ["system", "group", "measure", "source", "file"]
        metrics = metrics.assign(value=pd.to_numeric(metrics["value"]))
        if "by" in aggregate:
            repeated = metrics.duplicated(keys + ["_unit"], keep=False)
            if repeated.any():
                raise SourceError(
                    f"{self._label}: {metrics.loc[repeated, '_unit'].nunique()} of the {across} have more than one "
                    "row for the same system, group and measure; pick one with `where` or `latest`"
                )
            if aggregate.get("paired"):
                metrics = self._paired(metrics, across)
        elif aggregate.get("paired") or "wins" in aggregate["stats"]:
            raise SourceError(f"{self._label}: `paired` and `wins` need `by`, the column naming each of the {across}")
        grouped = metrics.groupby(keys, sort=False, dropna=False)["value"]
        frames = []
        for stat in aggregate["stats"]:
            if stat == "wins":
                frames.append(self._wins(metrics, aggregate, across))
                continue
            frame = grouped.agg(stat).reset_index()
            frame["measure"] = frame["measure"] + f", {stat} across {across}"
            frame["n"] = grouped.count().to_numpy()
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)

    def _paired(self, metrics: pd.DataFrame, across: str) -> pd.DataFrame:
        """Keep only what every system has a result for, so each system's statistics cover the same set."""
        kept = []
        for (group, measure), part in metrics.groupby(["group", "measure"], sort=False, dropna=False):
            systems = part["system"].nunique()
            complete = part.groupby("_unit")["system"].transform("nunique") == systems
            dropped = part.loc[~complete, "_unit"].nunique()
            if dropped:
                total = part["_unit"].nunique()
                print(
                    f"{self._label}: paired: left out {dropped} of {total} {across} missing a system "
                    f"({group}, {measure})",
                    file=sys.stderr,
                )
            kept.append(part[complete])
        return pd.concat(kept, ignore_index=True)

    def _wins(self, metrics: pd.DataFrame, aggregate: dict, across: str) -> pd.DataFrame:
        """For each system, how many of the units it beats the baseline on; ties don't count as wins."""
        baseline = aggregate.get("baseline")
        if baseline is None:
            raise SourceError(f"{self._label}: the `wins` statistic needs a `baseline` system")
        if baseline not in set(metrics["system"]):
            raise SourceError(f"{self._label}: no rows for the baseline system '{baseline}'")
        sign = -1 if aggregate.get("better") == "lower" else 1
        match = ["group", "measure", "_unit"]
        base = metrics.loc[metrics["system"] == baseline, match + ["value"]].rename(columns={"value": "_baseline"})
        joined = metrics[metrics["system"] != baseline].merge(base, on=match)
        joined["_win"] = sign * (joined["value"] - joined["_baseline"]) > 0
        keys = ["system", "group", "measure", "source", "file"]
        frame = (
            joined.groupby(keys, sort=False, dropna=False)
            .agg(value=("_win", "sum"), n=("_win", "size"))
            .reset_index()
        )
        frame["measure"] = frame["measure"] + f", wins over {baseline} across {across}"
        return frame

    def _read(self) -> pd.DataFrame:
        """Read every file the patterns match; `capture` turns named groups in each path into columns."""
        capture = re.compile(self._spec["capture"]) if "capture" in self._spec else None
        frames = []
        for pattern in self._patterns:
            for path in self._source.resolve(pattern):
                frame = self._source.read_table(path)
                if capture is not None:
                    match = capture.search(path)
                    if match is None:
                        raise SourceError(f"{path}: doesn't match capture {capture.pattern}")
                    frame = frame.assign(**match.groupdict())
                frames.append(frame)
        return pd.concat(frames, ignore_index=True)

    def _latest(self, table: pd.DataFrame) -> pd.DataFrame:
        """Keep each experiment's highest value of a column, such as the last tested checkpoint."""
        latest = self._spec.get("latest")
        if latest is None:
            return table
        column, per = latest["column"], latest["per"]
        order = pd.to_numeric(table[column], errors="coerce")
        if order.isna().any():
            raise SourceError(f"{self._label}: latest: column '{column}' has values that aren't numbers")
        highest = order.groupby([table[c] for c in per], dropna=False).transform("max")
        return table[order == highest]

    def _melt(self, table: pd.DataFrame) -> pd.DataFrame:
        """Turn a wide table (one column per project, say) into rows, so its columns can be filtered and renamed."""
        melt = self._spec.get("melt")
        if melt is None:
            return table
        return table.melt(id_vars=melt["keep"], var_name=melt["name"], value_name=melt["value"])

    def _filter(self, table: pd.DataFrame) -> pd.DataFrame:
        for column, allowed in self._spec.get("where", {}).items():
            allowed = [str(a) for a in allowed] if isinstance(allowed, list) else [str(allowed)]
            table = table[table[column].astype(str).isin(allowed)]
            if column != self._column_of(self._spec["system"]) and column != self._column_of(self._spec.get("group")):
                continue
            # Keep the order the spec lists values in, so tables and legends follow it.
            table = table.assign(_order=table[column].astype(str).map({v: i for i, v in enumerate(allowed)}))
            table = table.sort_values("_order", kind="stable").drop(columns="_order")
        return table

    def _parse(self, value, how: str | None):
        if how is None:
            return value
        if how == "leading-number":
            # silnlp writes BLEU as "67.06/85.38/72.24/62.90/55.22/0.986/10932/11089": the score, then its details.
            match = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(value))
            return float(match.group(1)) if match else None
        raise SourceError(f"{self._label}: unknown parse '{how}'")

    def _measure_columns(self, measure: dict) -> list[str]:
        return [measure[k] for k in ("column", "lower", "upper", "n") if k in measure]

    def _column_of(self, field) -> str | None:
        return field["column"] if isinstance(field, dict) else None

    def _resolve(self, field, row) -> str:
        if not isinstance(field, dict):
            return str(field)
        # Several columns join with dots, for names split around another part of a path, like the
        # configuration in `AE.<language>.hmm`; an optional capture that didn't match is skipped.
        columns = field["column"] if isinstance(field["column"], list) else [field["column"]]
        return ".".join(str(row[c]) for c in columns if pd.notna(row[c]) and row[c] != "")


class Recipe:
    """A private source's tables, read from where the private data is kept.

    `label-files` lists files beside the data mapping identifiers to public labels, so a project
    keeps one label across every study; a table's own `rename` entries win over them.
    """

    def __init__(self, source, draft_path: Path | None):
        self._source = source
        self._draft = draft_path is not None
        text = draft_path.read_text(encoding="utf-8") if self._draft else source.read_recipe()
        self._spec = yaml.safe_load(text)

    def tables(self) -> list[TableSpec]:
        labels = {}
        for path in self._spec.get("label-files", []):
            labels.update(yaml.safe_load(self._read(path)))
        specs = []
        for spec in self._spec["tables"]:
            specs.append(TableSpec({**spec, "rename": {**labels, **spec.get("rename", {})}}, self._source))
        return specs

    def _read(self, path: str) -> str:
        return self._source.read_worktree_text(path) if self._draft else self._source.read_text(path)


def build_metrics(
    study_dir: Path, checkouts: dict[str, Path], draft_recipes: dict[str, Path], bucket_root: Path | None, freeze: bool
) -> pd.DataFrame:
    sources_file = study_dir / "sources.yml"
    spec = yaml.safe_load(sources_file.read_text(encoding="utf-8"))
    site_root = Path(__file__).resolve().parent.parent
    sources = {}
    for source_id, source_spec in spec["sources"].items():
        if source_spec.get("bucket"):
            sources[source_id] = BucketSource(source_id, source_spec, bucket_root, freeze)
        elif source_spec.get("in-study"):
            sources[source_id] = StudySource(source_id, study_dir)
        else:
            checkout = checkouts.get(source_id, site_root.parent / source_id)
            sources[source_id] = GitSource(source_id, source_spec, checkout)
    tables = []
    for source in sources.values():
        source.check()
        if not source.is_public:
            tables += Recipe(source, draft_recipes.get(source.id)).tables()
    for table in spec.get("tables", []):
        source = sources.get(table["source"])
        if source is None:
            raise SourceError(f"{table['file']}: unknown source '{table['source']}'")
        if not source.is_public:
            raise SourceError(f"{table['file']}: source '{source.id}' is private, so its tables belong in its recipe")
        tables.append(TableSpec(table, source))
    metrics = pd.concat([table.extract() for table in tables], ignore_index=True)
    for source in sources.values():
        source.finish(sources_file)
    metrics["n"] = pd.to_numeric(metrics["n"]).astype("Int64")
    return metrics[metrics["value"].notna()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("study", type=Path, help="study folder, e.g. studies/2026-10-chrf-b")
    parser.add_argument("--checkout", action="append", default=[], metavar="SOURCE=PATH")
    parser.add_argument("--draft-recipe", action="append", default=[], metavar="SOURCE=PATH")
    parser.add_argument("--bucket-root", type=Path, default=os.getenv("SIL_NLP_DATA_PATH") or None)
    parser.add_argument("--freeze", action="store_true", help="copy bucket files and record a new snapshot")
    args = parser.parse_args()
    checkouts = {k: Path(v) for k, v in (c.split("=", 1) for c in args.checkout)}
    draft_recipes = {k: Path(v) for k, v in (c.split("=", 1) for c in args.draft_recipe)}
    bucket_root = Path(args.bucket_root) if args.bucket_root else None
    try:
        metrics = build_metrics(args.study, checkouts, draft_recipes, bucket_root, args.freeze)
    except (SourceError, KeyError, OSError) as e:
        sys.exit(f"error: {e}")
    out = args.study / "data" / "metrics.csv"
    out.parent.mkdir(exist_ok=True)
    metrics.to_csv(out, index=False, lineterminator="\n")
    print(f"wrote {len(metrics)} rows to {out}")
    if draft_recipes:
        print("draft recipe: commit it in the private repository and pin that commit before publishing")


if __name__ == "__main__":
    main()
