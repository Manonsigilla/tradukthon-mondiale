"""Parser des taxonomies Open Food Facts au format JSON.

Le fichier source (ex: categories.full.json) a la forme:
    { "en:lemon-balm": {
        "name": {"en": "Lemon balm", "fr": "Mélisse officinale", ...},
        "synonyms": {"en": ["Lemon balm"], "fr": ["Mélisse..."], ...},
        "parents": ["en:herbal-teas"],
        "children": [...],
        ...
      }, ... }

On en dérive deux DataFrames polars:
    entries: une ligne par entrée canonique (id, parents, n_languages, ...)
    labels:  une ligne par (entry_id, lang, label, is_synonym)
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl


def load_taxonomy_json(path: str | Path) -> dict:
    """Charge un fichier taxonomie OFF (JSON)."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


_ENTRIES_SCHEMA = {
    "id": pl.String,
    "taxonomy": pl.String,
    "prefix": pl.String,
    "parents": pl.List(pl.String),
    "n_parents": pl.UInt32,
    "n_children": pl.UInt32,
    "n_languages": pl.UInt32,
    "has_wikidata": pl.Boolean,
    "is_protected_name": pl.Boolean,
}

_LABELS_SCHEMA = {
    "id": pl.String,
    "taxonomy": pl.String,
    "lang": pl.String,
    "label": pl.String,
    "is_synonym": pl.Boolean,
}


def _build_entry_row(entry_id: str, props: dict, taxonomy_name: str) -> dict:
    """Build the 'entries' row for one canonical taxonomy concept."""
    name = props.get("name", {}) or {}
    synonyms = props.get("synonyms", {}) or {}
    parents = props.get("parents", []) or []
    children = props.get("children", []) or []
    langs = set(name.keys()) | set(synonyms.keys())
    return {
        "id": entry_id,
        "taxonomy": taxonomy_name,
        "prefix": entry_id.split(":", 1)[0] if ":" in entry_id else "",
        "parents": list(parents),
        "n_parents": len(parents),
        "n_children": len(children),
        "n_languages": len(langs),
        "has_wikidata": bool(props.get("wikidata")),
        "is_protected_name": bool(props.get("protected_name_type")),
    }


def _label_row(entry_id: str, taxonomy_name: str, lang: str, label: str, is_synonym: bool) -> dict:
    """Build one row of the 'labels' DataFrame. Centralises the row schema."""
    return {
        "id": entry_id,
        "taxonomy": taxonomy_name,
        "lang": lang,
        "label": label,
        "is_synonym": is_synonym,
    }


def _build_label_rows(entry_id: str, props: dict, taxonomy_name: str) -> list[dict]:
    """Yield all label rows (canonical names + synonyms) for one entry.

    The OFF JSON occasionally returns a list of strings for 'name' instead
    of a single string — we normalise that here. Synonyms equal to the
    canonical name for a language are skipped to avoid double-counting.
    """
    name = props.get("name", {}) or {}
    synonyms = props.get("synonyms", {}) or {}
    rows: list[dict] = []

    # canonical labels: one per language (sometimes a list of strings)
    for lang, label in name.items():
        if label is None:
            continue
        labels = label if isinstance(label, list) else [label]
        for lab in labels:
            rows.append(_label_row(entry_id, taxonomy_name, lang, str(lab), False))

    # synonyms: 0..n per language, deduplicated against the canonical label
    for lang, syns in synonyms.items():
        if not syns:
            continue
        if isinstance(syns, str):
            syns = [syns]
        canonical = name.get(lang)
        for syn in syns:
            if syn is None or syn == canonical:
                continue
            rows.append(_label_row(entry_id, taxonomy_name, lang, str(syn), True))

    return rows


def parse_taxonomy(raw: dict, taxonomy_name: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Transforme le dict brut en deux DataFrames polars.

    Returns
    -------
    entries: id, taxonomy, prefix, parents, n_parents, n_children, n_languages,
             has_wikidata, is_protected_name
    labels:  id, taxonomy, lang, label, is_synonym
    """
    entry_rows: list[dict] = []
    label_rows: list[dict] = []
    for entry_id, props in raw.items():
        entry_rows.append(_build_entry_row(entry_id, props, taxonomy_name))
        label_rows.extend(_build_label_rows(entry_id, props, taxonomy_name))

    entries = pl.DataFrame(entry_rows, schema=_ENTRIES_SCHEMA)
    labels = pl.DataFrame(label_rows, schema=_LABELS_SCHEMA)
    return entries, labels


def load_and_parse(path: str | Path, taxonomy_name: str | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Convenience: charge un fichier + parse en une étape."""
    path = Path(path)
    if taxonomy_name is None:
        # categories.full.json -> categories
        taxonomy_name = path.stem.split(".")[0]
    raw = load_taxonomy_json(path)
    return parse_taxonomy(raw, taxonomy_name)


def language_coverage(labels: pl.DataFrame) -> pl.DataFrame:
    """Pour chaque langue, nombre d'entrées qui ont au moins un label (canonique ou synonyme)."""
    total_entries = labels.select(pl.col("id").n_unique()).item()
    return (
        labels.group_by("lang")
        .agg(
            pl.col("id").n_unique().alias("n_entries_covered"),
            pl.col("label").len().alias("n_labels_total"),
            (pl.col("is_synonym").not_()).sum().alias("n_canonical_labels"),
        )
        .with_columns(
            (pl.col("n_entries_covered") / total_entries * 100).alias("pct_coverage"),
        )
        .sort("n_entries_covered", descending=True)
    )


def entries_completeness(labels: pl.DataFrame, top_n_langs: int | None = None) -> pl.DataFrame:
    """Pour chaque entrée, nombre de langues dans lesquelles elle est traduite.

    Si top_n_langs est fourni, restreint aux N langues les plus couvertes.
    """
    if top_n_langs is not None:
        top = language_coverage(labels).head(top_n_langs)["lang"].to_list()
        labels = labels.filter(pl.col("lang").is_in(top))
    return (
        labels.group_by("id", "taxonomy")
        .agg(pl.col("lang").n_unique().alias("n_langs"))
        .sort("n_langs", descending=True)
    )


def stats_summary(entries: pl.DataFrame, labels: pl.DataFrame) -> dict:
    """Renvoie un dict de chiffres clés pour le rapport."""
    return {
        "n_entries": entries.height,
        "n_root_entries": entries.filter(pl.col("n_parents") == 0).height,
        "n_leaf_entries": entries.filter(pl.col("n_children") == 0).height,
        "n_languages": labels["lang"].n_unique(),
        "n_labels_total": labels.height,
        "n_canonical_labels": int((~labels["is_synonym"]).sum()),
        "n_synonyms": int(labels["is_synonym"].sum()),
        "pct_with_wikidata": float(entries["has_wikidata"].mean() * 100),
        "avg_languages_per_entry": float(entries["n_languages"].mean()),
    }
