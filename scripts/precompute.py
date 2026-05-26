"""Pré-calcule TOUTES les métriques A/B/C/D et sauve les résultats en parquet
dans data/cache/. Idempotent : skip ce qui existe déjà.

Stratégie mémoire : pour les taxonomies à fan-out élevé (ingrédients : 30-50
tags par produit), on restreint le calcul aux pays présents dans
COUNTRY_LANGUAGES (~48 pays) — sinon le double-explode produits × pays × tags
fait sauter la RAM.

Lancer :
    python scripts/precompute.py            # idempotent
    python scripts/precompute.py --force    # tout recalculer
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
from pathlib import Path
from typing import Callable

import polars as pl

from src.loader import scan_products
from src.taxonomy import load_and_parse
from src.metrics import (
    country_labeling_rate,
    country_tag_canonical_coverage,
    country_language_deficit,
    unknown_tags,
    unknown_tags_by_country,
    dead_entries,
    used_entries_summary,
    COUNTRY_LANGUAGES,
    country_tag_to_iso,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

# Countries we evaluate for fan-out-heavy metrics. Keeps the cross-product
# (products × countries × ingredients) within RAM on a laptop.
USEFUL_COUNTRIES = list(COUNTRY_LANGUAGES.keys())


# ---------------------------------------------------------------------------
# Logging + caching helpers
# ---------------------------------------------------------------------------

def need(path: Path, force: bool) -> bool:
    """Return True if the cache file must be (re)computed."""
    if force or not path.exists():
        return True
    print(f"[skip] {path.name} existe déjà", flush=True)
    return False


def step(name: str) -> float:
    """Print a 'starting' line and return the start time."""
    t = time.time()
    print(f"[..] {name}", flush=True)
    return t


def done(t: float, name: str, df: pl.DataFrame | None = None) -> None:
    """Print a 'done' line with elapsed time and (optional) row count."""
    extra = f" ({df.height} rows)" if df is not None else ""
    print(f"[ok] {name} — {time.time() - t:.1f}s{extra}", flush=True)


def run_step(
    label: str,
    filename: str,
    compute: Callable[[], pl.DataFrame],
    force: bool,
    *,
    add_iso3: bool = False,
) -> None:
    """Compute a metric, persist it to data/cache/, log timing.

    Idempotent: skips the computation if the cache file already exists
    (unless ``force=True``). When ``add_iso3=True``, derives an ISO-3
    country code column for Plotly choropleth maps.
    """
    path = CACHE / filename
    if not need(path, force):
        return
    t = step(label)
    df = compute()
    if add_iso3:
        df = df.with_columns(
            pl.col("country")
            .map_elements(country_tag_to_iso, return_dtype=pl.String)
            .alias("iso3")
        )
    df.write_parquet(path)
    done(t, label, df)
    gc.collect()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    force = args.force

    print("== Chargement des taxonomies ==", flush=True)
    cat_e, cat_l = load_and_parse(RAW / "categories.full.json")
    if need(CACHE / "cat_entries.parquet", force):
        cat_e.write_parquet(CACHE / "cat_entries.parquet")
        cat_l.write_parquet(CACHE / "cat_labels.parquet")

    ing_e, ing_l = load_and_parse(RAW / "ingredients.full.json")
    if need(CACHE / "ing_entries.parquet", force):
        ing_e.write_parquet(CACHE / "ing_entries.parquet")
        ing_l.write_parquet(CACHE / "ing_labels.parquet")

    print("\n== Métriques côté produits ==", flush=True)

    # A fresh LazyFrame each step is cheap (lazy) and avoids any state leaks.
    def fresh_lf() -> pl.LazyFrame:
        return scan_products(RAW / "food.parquet")

    # products per country (used by 02-coverage)
    run_step(
        "products_by_country",
        "products_by_country.parquet",
        lambda: (
            fresh_lf()
            .select("code", "countries_tags")
            .filter(pl.col("countries_tags").is_not_null())
            .explode("countries_tags")
            .filter(pl.col("countries_tags").is_not_null())
            .group_by("countries_tags")
            .agg(pl.col("code").n_unique().alias("n_products"))
            .sort("n_products", descending=True)
            .collect()
        ),
        force,
    )

    # B1: labeling rate
    run_step(
        "B1 country_labeling_rate (categories)",
        "b1_labeling_rate.parquet",
        lambda: country_labeling_rate(fresh_lf(), "categories_tags", min_products=200),
        force,
        add_iso3=True,
    )

    # B2: canonical coverage (categories)
    run_step(
        "B2 canonical (categories)",
        "b2_canonical_cat.parquet",
        lambda: country_tag_canonical_coverage(fresh_lf(), cat_e, "categories_tags", min_products=200),
        force,
        add_iso3=True,
    )

    # B2 ingredients is skipped on purpose: the explode (products × countries
    # × ingredients) saturates RAM on a 7 GB parquet. The same analysis is
    # available via the Superset/DuckDB SQL (cf. sql/ + report/04-superset.qmd).
    print("[skip] B2 ingredients (volontairement, RAM)", flush=True)

    # C: country × language deficit
    run_step(
        "C deficit (categories)",
        "c_deficit_cat.parquet",
        lambda: country_language_deficit(fresh_lf(), cat_l, "categories_tags", COUNTRY_LANGUAGES, min_products=500),
        force,
    )

    # C ingredients: same RAM issue as B2 ingredients, see Superset.
    print("[skip] C ingredients (volontairement, RAM)", flush=True)

    # D1 summary: a dict, not a DataFrame, so we handle it inline.
    if need(CACHE / "d1_summary_cat.parquet", force):
        t = step("D1 used_entries_summary (categories)")
        s = used_entries_summary(fresh_lf(), cat_e, "categories_tags")
        pl.DataFrame([s]).write_parquet(CACHE / "d1_summary_cat.parquet")
        done(t, "D1 summary")
        gc.collect()

    # D1 dead entries (taxonomy entries never used by any product)
    run_step(
        "D1 dead_entries (categories)",
        "d1_dead_cat.parquet",
        lambda: dead_entries(fresh_lf(), cat_e, "categories_tags"),
        force,
    )

    # D2 unknown tags (categories) — restricted to useful countries to keep
    # the cross-product manageable.
    run_step(
        "D2 unknown_tags (categories) - restreint pays",
        "d2_unknown_cat.parquet",
        lambda: unknown_tags(fresh_lf(), cat_e, "categories_tags", top_n=50, country_filter=USEFUL_COUNTRIES),
        force,
    )

    # D2 ingredients: skipped (RAM, see B2 ing).
    print("[skip] D2 ingredients (volontairement, RAM)", flush=True)

    # D2 per-country (feeds the Plotly dropdown on 03-gaps).
    if need(CACHE / "d2_unknown_by_country.parquet", force):
        top_countries = [
            "en:france", "en:united-states", "en:germany", "en:spain", "en:italy",
            "en:united-kingdom", "en:belgium", "en:switzerland", "en:netherlands", "en:poland",
        ]
        per_country: list[pl.DataFrame] = []
        for c in top_countries:
            t = step(f"D2 by_country {c}")
            df = unknown_tags_by_country(fresh_lf(), cat_e, "categories_tags", c, top_n=20)
            df = df.with_columns(pl.lit(c).alias("country"))
            per_country.append(df)
            done(t, f"  {c}", df)
            gc.collect()
        if per_country:
            pl.concat(per_country).write_parquet(CACHE / "d2_unknown_by_country.parquet")

    print(f"\n[done] Cache écrit dans {CACHE}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
