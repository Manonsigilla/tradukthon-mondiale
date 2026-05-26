"""Lecture du parquet Open Food Facts (lazy + projection).

Le parquet OFF (~7 Go, ~4 M produits) contient une centaine de colonnes.
On ne charge QUE celles utiles à l'analyse de couverture taxonomique :

    code              : identifiant produit
    lang              : langue principale du produit
    countries_tags    : list[str], pays où le produit est vendu (ex: 'en:france')
    categories_tags   : list[str], ex: 'en:beverages'
    ingredients_tags  : list[str], ex: 'en:water'
    languages_tags    : list[str], langues détectées sur le produit

Toutes les fonctions renvoient des LazyFrame quand possible, pour permettre
au moteur d'optimiser les projections/filtres avant collect().
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

DEFAULT_COLS = [
    "code",
    "lang",
    "countries_tags",
    "categories_tags",
    "ingredients_tags",
    "languages_tags",
]


def scan_products(parquet_path: str | Path, columns: list[str] | None = None) -> pl.LazyFrame:
    """Renvoie un LazyFrame avec uniquement les colonnes demandées.

    Le scan_parquet de polars pousse la projection au moteur Arrow,
    donc lire 6 colonnes sur 80 est ~10x plus rapide qu'un read complet.
    """
    cols = columns or DEFAULT_COLS
    lf = pl.scan_parquet(str(parquet_path))
    # certaines colonnes peuvent ne pas exister selon la version du dump
    available = lf.collect_schema().names()
    cols = [c for c in cols if c in available]
    return lf.select(cols)


def explode_tags(
    lf: pl.LazyFrame,
    tag_col: str,
    country_col: str = "countries_tags",
    country_filter: list[str] | None = None,
) -> pl.LazyFrame:
    """Renvoie un LazyFrame (code, country, tag) en exploitant les listes.

    Le double-explode est l'opération de base pour croiser produits × pays × tags.

    ``country_filter`` (optionnel) restreint AVANT explode au sous-ensemble
    de pays donné — indispensable pour les taxonomies à fan-out élevé
    (ingrédients : 30-50 tags par produit) qui sinon font sauter la RAM.
    """
    out = (
        lf.select("code", country_col, tag_col)
        .filter(pl.col(tag_col).is_not_null())
        .filter(pl.col(country_col).is_not_null())
    )
    if country_filter is not None:
        # filter sur la list[str] : au moins une intersection
        out = out.filter(pl.col(country_col).list.eval(pl.element().is_in(country_filter)).list.any())
    out = (
        out.explode(country_col)
        .filter(pl.col(country_col).is_not_null())
    )
    if country_filter is not None:
        out = out.filter(pl.col(country_col).is_in(country_filter))
    out = (
        out.explode(tag_col)
        .filter(pl.col(tag_col).is_not_null())
        .rename({country_col: "country", tag_col: "tag"})
    )
    return out
