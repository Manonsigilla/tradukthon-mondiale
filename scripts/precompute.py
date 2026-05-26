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

# Pays restreints pour éviter les explosions mémoire sur ingrédients.
# Inclut tous les top pays OFF + les pays multilingues notables.
USEFUL_COUNTRIES = list(COUNTRY_LANGUAGES.keys())


def need(path: Path, force: bool) -> bool:
    if force or not path.exists():
        return True
    print(f"[skip] {path.name} existe déjà", flush=True)
    return False


def step(name: str):
    t = time.time()
    print(f"[..] {name}", flush=True)
    return t


def done(t: float, name: str, df: pl.DataFrame | None = None):
    extra = f" ({df.height} rows)" if df is not None else ""
    print(f"[ok] {name} — {time.time() - t:.1f}s{extra}", flush=True)


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

    def fresh_lf():
        # un nouveau LazyFrame à chaque étape — pas plus coûteux (lazy)
        return scan_products(RAW / "food.parquet")

    # --- products_by_country
    if need(CACHE / "products_by_country.parquet", force):
        t = step("products_by_country")
        by_country = (
            fresh_lf()
            .select("code", "countries_tags")
            .filter(pl.col("countries_tags").is_not_null())
            .explode("countries_tags")
            .filter(pl.col("countries_tags").is_not_null())
            .group_by("countries_tags")
            .agg(pl.col("code").n_unique().alias("n_products"))
            .sort("n_products", descending=True)
            .collect()
        )
        by_country.write_parquet(CACHE / "products_by_country.parquet")
        done(t, "by_country", by_country)
        del by_country
        gc.collect()

    # --- B1
    if need(CACHE / "b1_labeling_rate.parquet", force):
        t = step("B1 country_labeling_rate (categories)")
        r = country_labeling_rate(fresh_lf(), "categories_tags", min_products=200)
        r = r.with_columns(
            pl.col("country").map_elements(country_tag_to_iso, return_dtype=pl.String).alias("iso3")
        )
        r.write_parquet(CACHE / "b1_labeling_rate.parquet")
        done(t, "B1", r)
        del r
        gc.collect()

    # --- B2 categories
    if need(CACHE / "b2_canonical_cat.parquet", force):
        t = step("B2 canonical (categories)")
        cov_cat = country_tag_canonical_coverage(fresh_lf(), cat_e, "categories_tags", min_products=200)
        cov_cat = cov_cat.with_columns(
            pl.col("country").map_elements(country_tag_to_iso, return_dtype=pl.String).alias("iso3")
        )
        cov_cat.write_parquet(CACHE / "b2_canonical_cat.parquet")
        done(t, "B2 cat", cov_cat)
        del cov_cat
        gc.collect()

    # --- B2 ingredients : SKIP (explode ingrédients × pays sature la RAM
    #     sur ce dataset 7 Go). On garde la métrique pour les catégories
    #     uniquement, qui est l'angle critique pour le rapport.
    print("[skip] B2 ingredients (volontairement, RAM)", flush=True)

    # --- C cat
    if need(CACHE / "c_deficit_cat.parquet", force):
        t = step("C deficit (categories)")
        def_cat = country_language_deficit(fresh_lf(), cat_l, "categories_tags", COUNTRY_LANGUAGES, min_products=500)
        def_cat.write_parquet(CACHE / "c_deficit_cat.parquet")
        done(t, "C cat", def_cat)
        del def_cat
        gc.collect()

    # --- C ingredients : SKIP (idem B2 ing — l'explode ingrédients × pays
    #     fait segfault sur 7 Go de parquet). Le déficit catégories suffit
    #     pour le récit principal.
    print("[skip] C ingredients (volontairement, RAM)", flush=True)

    # --- D1 summary
    if need(CACHE / "d1_summary_cat.parquet", force):
        t = step("D1 used_entries_summary (categories)")
        s = used_entries_summary(fresh_lf(), cat_e, "categories_tags")
        pl.DataFrame([s]).write_parquet(CACHE / "d1_summary_cat.parquet")
        done(t, "D1 summary")
        gc.collect()

    # --- D1 dead
    if need(CACHE / "d1_dead_cat.parquet", force):
        t = step("D1 dead_entries (categories)")
        d = dead_entries(fresh_lf(), cat_e, "categories_tags")
        d.write_parquet(CACHE / "d1_dead_cat.parquet")
        done(t, "D1 dead cat", d)
        del d
        gc.collect()

    # --- D2 cat global (restreint pays utiles pour économiser RAM)
    if need(CACHE / "d2_unknown_cat.parquet", force):
        t = step("D2 unknown_tags (categories) - restreint pays")
        u = unknown_tags(fresh_lf(), cat_e, "categories_tags", top_n=50, country_filter=USEFUL_COUNTRIES)
        u.write_parquet(CACHE / "d2_unknown_cat.parquet")
        done(t, "D2 cat", u)
        del u
        gc.collect()

    # --- D2 ingredients : SKIP (RAM, voir B2 ing)
    print("[skip] D2 ingredients (volontairement, RAM)", flush=True)

    # --- D2 par pays (pour le dropdown)
    if need(CACHE / "d2_unknown_by_country.parquet", force):
        top_countries = [
            "en:france", "en:united-states", "en:germany", "en:spain", "en:italy",
            "en:united-kingdom", "en:belgium", "en:switzerland", "en:netherlands", "en:poland",
        ]
        per_country = []
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
