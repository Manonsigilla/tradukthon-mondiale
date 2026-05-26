"""Génère les CSV à uploader dans Superset comme datasets secondaires.

Ces datasets permettent de joindre les données du parquet OFF
(sql.openfoodfacts.org) à la taxonomie locale OFF.

Output dans `data/exports/`:
    taxonomy_categories.csv   (id, taxonomy, prefix, n_languages, has_wikidata)
    taxonomy_labels.csv       (id, lang)        — pour les JOIN de traduction
    country_languages.csv     (country, lang)   — pour la métrique C
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from src.taxonomy import load_and_parse
from src.metrics import COUNTRY_LANGUAGES

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "exports"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    print("== Export pour Superset ==")

    # 1) taxonomy_categories
    cat_e, cat_l = load_and_parse(RAW / "categories.full.json")
    cat_e.select("id", "taxonomy", "prefix", "n_languages", "has_wikidata", "is_protected_name").write_csv(
        OUT / "taxonomy_categories.csv"
    )
    print(f"  [ok] {OUT / 'taxonomy_categories.csv'} ({cat_e.height} lignes)")

    # 2) taxonomy_labels (unique sur id, lang — un produit JOIN doit savoir si la traduction existe)
    cat_l.select("id", "lang").unique().write_csv(OUT / "taxonomy_labels.csv")
    print(f"  [ok] {OUT / 'taxonomy_labels.csv'} ({cat_l.select('id', 'lang').unique().height} lignes)")

    # 3) country_languages (issue de notre mapping local)
    rows = []
    for country, langs in COUNTRY_LANGUAGES.items():
        for lang in langs:
            rows.append({"country": country, "lang": lang})
    pl.DataFrame(rows).write_csv(OUT / "country_languages.csv")
    print(f"  [ok] {OUT / 'country_languages.csv'} ({len(rows)} lignes)")

    print("\nUploader ces 3 CSV dans Superset comme datasets, puis lancer les SQL.")


if __name__ == "__main__":
    main()
