"""Search a study for the real identifiers behind its experiment-bucket sources.

Usage:
    uv run rs-check-bucket studies/<study> [--bucket-root M:/]

The identifiers are read from the bucket on every run and never written down, so neither this file
nor the study names them, and a new project is covered the day its data reaches the bucket:

- the code of every Scripture file in MT/scripture (`<iso>-<Name>`, with and without its date);
- for the study's own experiments, found from the files frozen for it: their folder names, their ISO
  codes, and the project codes in their results and configs, with each project's bare name;
- every identifier the recipes' label files map to a label.

Bare names and ISO codes are checked only for the study's own experiments: across thousands of
projects, short names collide with ordinary words. A study's `allowed-terms`, and the codes and
Bibles of the major languages it may name, are skipped.

It prints each line that names an identifier and exits 1, or exits 0 when the study is clean. It needs
the bucket, so it runs where the study is drafted, not in CI.
"""

import argparse
import os
import re
import sys
from pathlib import Path, PurePosixPath

import pandas as pd
import yaml

from research_site.validate import TEXT_SUFFIXES

# A Scripture file is `<language>-<Name>`, often with a date and a script after it. Both parts take
# many shapes (`<iso>L`, `<iso>bt`, names with dots, plus signs or spaces), so anything with a hyphen counts.
CODE = re.compile(r"[A-Za-z]\w*-.+")
DATE = re.compile(r"_\d{4}[_-]\d{2}[_-]\d{2}.*$")
ISO_COLUMNS = ("src_iso", "trg_iso")
# Widely published languages, which a study may name; their texts are published Bibles (en-BSB).
MAJOR_LANGUAGES = {"en", "eng", "fr", "fra", "es", "spa", "pt", "por", "de", "deu", "ru", "rus", "zh", "zho"}


def scripture_codes(root: Path) -> set[str]:
    codes = set()
    for path in (root / "MT" / "scripture").glob("*.txt"):
        if CODE.fullmatch(path.stem):
            codes |= {path.stem, DATE.sub("", path.stem)}
    return codes


def word_pattern(terms: set[str]) -> re.Pattern:
    """Matches any term as a whole word, counting hyphens as part of a word, so a project's bare name
    doesn't match inside another code."""
    if not terms:
        return re.compile(r"(?!)")
    alternatives = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])({alternatives})(?![\w-])", re.IGNORECASE)


def study_terms(root: Path, recipe: str, codes: set[str]) -> tuple[set[str], set[str]]:
    """(identifiers, ISO codes) of the experiments a recipe's frozen files came from."""
    recipe_dir = PurePosixPath(recipe).parent
    files_dir = root / recipe_dir / "files"
    if not files_dir.is_dir():
        sys.exit(f"error: nothing frozen for {recipe}; run rs-import with --freeze first")
    terms, isos, texts = set(), set(), []
    experiments = set()
    for path in files_dir.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(files_dir).parts
        if parts[:2] == ("MT", "experiments"):
            terms.update(parts[2:-1])
            experiments.add(Path(*parts[:-1]))
        text = path.read_text(encoding="utf-8", errors="replace")
        texts.append(text)
        if path.suffix in (".csv", ".tsv"):
            table = pd.read_csv(path, sep="\t" if path.suffix == ".tsv" else ",", dtype=str)
            for column in ISO_COLUMNS:
                if column in table:
                    isos.update(table[column].dropna())
    # Configs name the corpus projects but aren't imported, so they're read from the experiment itself.
    for experiment in experiments:
        config = root / experiment / "config.yml"
        if config.is_file():
            texts.append(config.read_text(encoding="utf-8", errors="replace"))
    known = word_pattern(codes)
    for text in texts:
        for match in known.finditer(text):
            code = DATE.sub("", match.group(1))
            iso, name = code.split("-", 1)
            iso = iso.lower()
            terms |= {match.group(1), code}
            isos.add(iso)
            if iso not in MAJOR_LANGUAGES:
                terms.add(name)

    labels = yaml.safe_load((root / recipe).read_text(encoding="utf-8")).get("label-files", [])
    for label_file in labels:
        frozen = files_dir / label_file
        mapping = yaml.safe_load((frozen if frozen.is_file() else root / label_file).read_text(encoding="utf-8"))
        terms.update(str(key) for key in mapping or {})
    return terms, isos - MAJOR_LANGUAGES


def allowed_terms(study: Path) -> set[str]:
    index = study / "index.qmd"
    match = re.match(r"---\r?\n(.*?)\r?\n---", index.read_text(encoding="utf-8"), re.DOTALL) if index.exists() else None
    front_matter = yaml.safe_load(match.group(1)) if match else {}
    return {str(t).lower() for t in (front_matter or {}).get("allowed-terms", [])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("study", type=Path)
    parser.add_argument("--bucket-root", type=Path, default=os.getenv("SIL_NLP_DATA_PATH") or None)
    args = parser.parse_args()
    if args.bucket_root is None:
        sys.exit("error: set SIL_NLP_DATA_PATH or pass --bucket-root")
    sources = yaml.safe_load((args.study / "sources.yml").read_text(encoding="utf-8"))["sources"]
    recipes = [s["recipe"] for s in sources.values() if s.get("bucket")]
    if not recipes:
        sys.exit(f"error: {args.study} has no bucket source")

    codes = scripture_codes(args.bucket_root)
    own, isos = set(), set()
    for recipe in recipes:
        terms, recipe_isos = study_terms(args.bucket_root, recipe, codes)
        own |= terms
        isos |= recipe_isos
    allowed = allowed_terms(args.study)
    terms = {t for t in codes | own | isos if t.lower() not in allowed}
    pattern = word_pattern(terms)

    files = sorted(p for p in args.study.rglob("*") if p.suffix.lower() in TEXT_SUFFIXES)
    print(
        f"checking {len(files)} files for {len(codes)} project codes and {len(own | isos)} identifiers "
        "from this study's experiments"
    )
    found = 0
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hits = sorted({m.group(1) for m in pattern.finditer(line)})
            if hits:
                found += 1
                print(f"{path.relative_to(args.study).as_posix()}:{number}: names {', '.join(hits)}")
    if found:
        sys.exit(f"{found} lines name a real identifier; replace each with its label or leave it out")
    print("clean: no identifier from the bucket in this study")


if __name__ == "__main__":
    main()
