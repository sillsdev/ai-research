"""Check every study folder before it reaches the public site.

Usage:
    uv run rs-validate                  # all studies
    uv run rs-validate studies/<study>  # one study

This is the structural gate that can run in public CI. It cannot know a harness's private project
codes or corpus text, so it is a backstop to the harness skill's own anonymization pass, not a
replacement for it.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import pycountry
import yaml

ALLOWED_SUFFIXES = {".qmd", ".md", ".csv", ".yml", ".yaml", ".png", ".svg", ".jpg", ".jpeg", ".webp"}
TEXT_SUFFIXES = {".qmd", ".md", ".csv", ".yml", ".yaml"}
MAX_FILE_BYTES = 500_000
# Summary tables run to hundreds of rows; thousands means per-verse or per-segment data was copied.
MAX_METRICS_ROWS = 5_000
REQUIRED_FRONT_MATTER = ["title", "description", "date", "author", "harness"]
REQUIRED_METRICS_COLUMNS = ["system", "group", "measure", "value"]


class StudyCheck:
    def __init__(self, directory: Path, harnesses: set[str], countries: list[str]):
        self._dir = directory
        self._harnesses = harnesses
        self._countries = countries
        self._private_sources: set[str] = set()
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def run(self) -> None:
        front_matter = self._check_front_matter()
        self._check_files()
        self._check_sources()
        self._check_metrics()
        self._check_review_notes()
        self._check_place_names(set(front_matter.get("allowed-terms", [])))

    def _check_front_matter(self) -> dict:
        index = self._dir / "index.qmd"
        if not index.exists():
            self.errors.append("missing index.qmd")
            return {}
        match = re.match(r"---\r?\n(.*?)\r?\n---", index.read_text(encoding="utf-8"), re.DOTALL)
        front_matter = yaml.safe_load(match.group(1)) if match else None
        if not isinstance(front_matter, dict):
            self.errors.append("index.qmd has no YAML front matter")
            return {}
        for key in REQUIRED_FRONT_MATTER:
            if not front_matter.get(key):
                self.errors.append(f"index.qmd front matter is missing '{key}'")
        harness = front_matter.get("harness")
        if harness and harness not in self._harnesses:
            self.errors.append(f"harness '{harness}' has no skill in .claude/skills (known: {sorted(self._harnesses)})")
        return front_matter

    def _check_files(self) -> None:
        for path in self._dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self._dir)
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                self.errors.append(f"{relative}: file type not allowed in a study")
            elif path.stat().st_size > MAX_FILE_BYTES:
                self.errors.append(f"{relative}: over {MAX_FILE_BYTES // 1000} KB; a study holds summaries only")

    def _check_metrics(self) -> None:
        path = self._dir / "data" / "metrics.csv"
        if not path.exists():
            self.errors.append("missing data/metrics.csv")
            return
        metrics = pd.read_csv(path)
        missing = [c for c in REQUIRED_METRICS_COLUMNS if c not in metrics.columns]
        if missing:
            self.errors.append(f"data/metrics.csv is missing columns {missing}")
            return
        if len(metrics) > MAX_METRICS_ROWS:
            self.errors.append(f"data/metrics.csv has {len(metrics)} rows; summaries only (limit {MAX_METRICS_ROWS})")
        if not pd.api.types.is_numeric_dtype(metrics["value"]):
            self.errors.append("data/metrics.csv: 'value' is not numeric")
            return
        if {"source", "file"} <= set(metrics.columns):
            leaked = metrics[metrics["source"].isin(self._private_sources) & metrics["file"].notna()]
            if len(leaked):
                self.errors.append(f"data/metrics.csv: {len(leaked)} rows name a private source's files; re-run rs-import")
        if {"lower", "upper"} <= set(metrics.columns):
            outside = metrics[(metrics["value"] < metrics["lower"]) | (metrics["value"] > metrics["upper"])]
            for _, row in outside.iterrows():
                self.warnings.append(
                    f"data/metrics.csv: {row['system']} / {row['group']} / {row['measure']} lies outside its interval"
                )

    def _check_sources(self) -> None:
        path = self._dir / "sources.yml"
        if not path.exists():
            self.errors.append("missing sources.yml")
            return
        spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for source_id, source in spec.get("sources", {}).items():
            where = f"sources.yml: source '{source_id}'"
            if source.get("bucket"):
                self._check_bucket_source(where, source_id, source)
                continue
            if not re.fullmatch(r"[0-9a-f]{7,40}", str(source.get("commit", ""))):
                self.errors.append(f"{where} needs a commit hash")
            repo = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)", str(source.get("repo", "")))
            if not repo:
                self.errors.append(f"{where} needs a GitHub repo URL")
            visibility = source.get("visibility")
            if visibility == "private":
                self._private_sources.add(source_id)
                if not source.get("recipe"):
                    self.errors.append(f"{where} is private, so it needs a 'recipe' in that repository")
            elif visibility == "public":
                if repo:
                    self._check_public(where, repo.group(1))
            else:
                self.errors.append(f"{where} needs 'visibility: public' or 'visibility: private'")
        for table in spec.get("tables", []):
            if table.get("source") in self._private_sources:
                self.errors.append(
                    f"sources.yml: table {table.get('file')} names private source '{table['source']}'; "
                    "its tables belong in the recipe, since they name private files and identifiers"
                )

    def _check_bucket_source(self, where: str, source_id: str, source: dict) -> None:
        self._private_sources.add(source_id)
        if source.get("visibility") != "private":
            self.errors.append(f"{where} is the experiment store, which is private: set 'visibility: private'")
        if not source.get("recipe"):
            self.errors.append(f"{where} needs a 'recipe' in the bucket")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(source.get("snapshot", ""))):
            self.errors.append(f"{where} needs a snapshot; run rs-import with --freeze")

    def _check_public(self, where: str, repo: str) -> None:
        # Unauthenticated, so a private repository answers 404 just like a missing one.
        try:
            with urllib.request.urlopen(f"https://api.github.com/repos/{repo}", timeout=15) as response:
                is_public = not json.load(response).get("private", True)
        except urllib.error.HTTPError as e:
            is_public = e.code != 404
            if is_public:
                self.warnings.append(f"{where}: couldn't confirm {repo} is public (HTTP {e.code})")
                return
        except OSError as e:
            self.warnings.append(f"{where}: couldn't confirm {repo} is public ({e})")
            return
        if not is_public:
            self.errors.append(
                f"{where}: {repo} is not public. Mark it 'visibility: private' and move its tables to a recipe "
                "there, or make the repository public"
            )

    def _check_review_notes(self) -> None:
        for path in sorted(self._dir.rglob("*.qmd")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "REVIEW:" in line:
                    self.errors.append(f"{path.relative_to(self._dir)}:{number}: unresolved REVIEW note")

    def _check_place_names(self, allowed: set[str]) -> None:
        for path in sorted(self._dir.rglob("*")):
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8")
            found = sorted({c for c in self._countries if c not in allowed and re.search(rf"\b{re.escape(c)}\b", text)})
            if found:
                self.errors.append(
                    f"{path.relative_to(self._dir)}: names {', '.join(found)}. Anonymize it, or list it under "
                    "'allowed-terms' in the front matter if it is safe to publish (a Biblical place, a public dataset)"
                )


def country_names() -> list[str]:
    names = set()
    for country in pycountry.countries:
        names.add(country.name)
        if hasattr(country, "common_name"):
            names.add(country.common_name)
    return sorted(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("studies", nargs="*", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    harnesses = {p.name.removeprefix("harness-") for p in (root / ".claude" / "skills").glob("harness-*")}
    studies = args.studies or sorted(p for p in (root / "studies").iterdir() if p.is_dir() and not p.name.startswith("_"))
    countries = country_names()
    failed = False
    for directory in studies:
        check = StudyCheck(directory, harnesses, countries)
        check.run()
        for warning in check.warnings:
            print(f"warning: {directory.name}: {warning}")
        for error in check.errors:
            print(f"error: {directory.name}: {error}")
        failed |= bool(check.errors)
        if not check.errors:
            print(f"ok: {directory.name}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
