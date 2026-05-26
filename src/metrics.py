"""Les 4 métriques de couverture du rapport.

Conventions
-----------
- ``entries`` / ``labels`` : DataFrames produits par :mod:`src.taxonomy` pour
  une (ou plusieurs) taxonomies.
- ``products`` : LazyFrame produits issu de :mod:`src.loader`.
- Un *tag* est un id de la forme ``"en:lemon-balm"`` (préfixe = code langue).
- Un pays est aussi un tag de la forme ``"en:france"``.

Grille A / B / C / D
--------------------
A. **Complétude de la taxonomie elle-même** — pour chaque langue, ratio
   d'entrées canoniques traduites. Voir :func:`language_completeness_score`.
B. **Couverture des produits par pays**
   - B1 :func:`country_labeling_rate` — % de produits ayant au moins un tag
   - B2 :func:`country_tag_canonical_coverage` — % de tags canoniques parmi
     ceux étiquetés
C. **Couverture utile pays × langue** — :func:`country_language_deficit`
   croise les entrées effectivement utilisées dans le pays avec les langues
   officielles parlées.
D. **Trous des deux côtés**
   - D1 :func:`dead_entries` — entrées taxonomie jamais utilisées
   - D2 :func:`unknown_tags` — tags utilisés mais absents de la taxonomie
"""

from __future__ import annotations

import polars as pl

from src.loader import explode_tags


# ---------------------------------------------------------------------------
# B1. Taux d'étiquetage des produits par pays
# ---------------------------------------------------------------------------

def country_labeling_rate(
    products: pl.LazyFrame,
    tag_col: str = "categories_tags",
    min_products: int = 50,
) -> pl.DataFrame:
    """B1 — par pays, % de produits ayant *au moins un* tag dans ``tag_col``.

    Mesure indépendante de la qualité de la taxonomie : un pays peut
    avoir un taux d'étiquetage élevé mais des tags massivement non-canoniques
    (ou l'inverse).

    Returns
    -------
    country, n_products_total, n_products_tagged, pct_tagged
    """
    has_tag = (
        products.select("code", "countries_tags", tag_col)
        .filter(pl.col("countries_tags").is_not_null())
        .explode("countries_tags")
        .filter(pl.col("countries_tags").is_not_null())
        .with_columns(
            # un produit est "étiqueté" si sa liste de tags est non null ET non vide
            (
                pl.col(tag_col).is_not_null()
                & (pl.col(tag_col).list.len() > 0)
            ).alias("tagged")
        )
        .rename({"countries_tags": "country"})
        .group_by("country")
        .agg(
            pl.col("code").n_unique().alias("n_products_total"),
            pl.col("tagged").sum().alias("n_products_tagged"),
        )
        .with_columns(
            (pl.col("n_products_tagged") / pl.col("n_products_total") * 100).alias("pct_tagged"),
        )
        .filter(pl.col("n_products_total") >= min_products)
        .sort("n_products_total", descending=True)
        .collect()
    )
    return has_tag


# ---------------------------------------------------------------------------
# B2. Couverture pays (qualité des tags étiquetés)
# ---------------------------------------------------------------------------

def country_tag_canonical_coverage(
    products: pl.LazyFrame,
    entries: pl.DataFrame,
    tag_col: str,
    min_products: int = 50,
    country_filter: list[str] | None = None,
) -> pl.DataFrame:
    """% de tags ``tag_col`` qui sont des entrées canoniques de la taxonomie,
    par pays.

    Returns: country, n_products, n_tag_occurrences, n_canonical, pct_canonical
    """
    canonical_ids = set(entries["id"].to_list())

    tags = explode_tags(products, tag_col, country_filter=country_filter).collect()

    by_country = (
        tags.with_columns(pl.col("tag").is_in(canonical_ids).alias("is_canonical"))
        .group_by("country")
        .agg(
            pl.col("code").n_unique().alias("n_products"),
            pl.col("tag").len().alias("n_tag_occurrences"),
            pl.col("is_canonical").sum().alias("n_canonical"),
        )
        .with_columns(
            (pl.col("n_canonical") / pl.col("n_tag_occurrences") * 100).alias("pct_canonical"),
        )
        .filter(pl.col("n_products") >= min_products)
        .sort("n_products", descending=True)
    )
    return by_country


# ---------------------------------------------------------------------------
# B. Complétude multilingue (taxonomie seule, pas besoin du parquet)
# ---------------------------------------------------------------------------

def multilingual_completeness_matrix(labels: pl.DataFrame) -> pl.DataFrame:
    """Matrice large entry × langue (booléen).

    Utile pour la heatmap et pour identifier les entrées orphelines par langue.
    """
    return (
        labels.select("id", "lang")
        .unique()
        .with_columns(pl.lit(1).alias("present"))
        .pivot(index="id", on="lang", values="present", aggregate_function="first")
        .fill_null(0)
    )


def language_completeness_score(labels: pl.DataFrame, entries: pl.DataFrame) -> pl.DataFrame:
    """Pour chaque langue: % d'entrées couvertes + score 'qualité'
    (présence de synonymes en plus du label canonique).
    """
    n_entries = entries.height
    per_lang_entries = (
        labels.group_by("lang")
        .agg(
            pl.col("id").n_unique().alias("n_entries_covered"),
            (~pl.col("is_synonym")).sum().alias("n_canonical_labels"),
            pl.col("is_synonym").sum().alias("n_synonym_labels"),
        )
        .with_columns(
            (pl.col("n_entries_covered") / n_entries * 100).alias("pct_coverage"),
            (pl.col("n_synonym_labels") / pl.col("n_canonical_labels")).alias("synonyms_per_canonical"),
        )
        .sort("pct_coverage", descending=True)
    )
    return per_lang_entries


# ---------------------------------------------------------------------------
# C. Déficit pays × langue (la métrique star)
# ---------------------------------------------------------------------------

def country_language_deficit(
    products: pl.LazyFrame,
    labels: pl.DataFrame,
    tag_col: str,
    country_languages: dict[str, list[str]],
    min_products: int = 100,
) -> pl.DataFrame:
    """Pour chaque (pays, langue parlée dans ce pays), pourcentage d'entrées
    taxonomiques *utilisées dans ce pays* qui n'ont PAS de traduction dans
    cette langue.

    Paramètres
    ----------
    products
        LazyFrame complet (lazily projeté).
    labels
        DataFrame issu de :func:`taxonomy.parse_taxonomy`.
    tag_col
        ``"categories_tags"`` ou ``"ingredients_tags"``.
    country_languages
        Mapping pays_tag (ex ``"en:france"``) -> liste de codes langues
        (ex ``["fr"]``). Voir :func:`build_country_languages`.

    Returns
    -------
    country, lang, n_entries_used, n_translated, n_missing, pct_deficit
    """
    # 1. quels ids canoniques sont utilisés dans chaque pays ?
    canonical_ids = labels["id"].unique().to_list()
    used = (
        explode_tags(products, tag_col, country_filter=list(country_languages.keys()))
        .filter(pl.col("tag").is_in(canonical_ids))
        .select("country", "tag")
        .unique()
        .collect()
    )

    # 2. pour chaque (id, lang), label existe ?
    has_label = labels.select("id", "lang").unique().with_columns(pl.lit(True).alias("has"))

    # 3. table (country, lang_attendue)
    cl = pl.DataFrame(
        {
            "country": list(country_languages.keys()),
            "expected_langs": [list(v) for v in country_languages.values()],
        }
    ).explode("expected_langs").rename({"expected_langs": "lang"})

    # 4. cross-join used × langues attendues du pays
    joined = used.join(cl, on="country", how="inner")
    # check translation
    joined = joined.join(has_label, left_on=["tag", "lang"], right_on=["id", "lang"], how="left")
    joined = joined.with_columns(pl.col("has").fill_null(False))

    out = (
        joined.group_by(["country", "lang"])
        .agg(
            pl.col("tag").n_unique().alias("n_entries_used"),
            pl.col("has").sum().alias("n_translated"),
        )
        .with_columns(
            (pl.col("n_entries_used") - pl.col("n_translated")).alias("n_missing"),
            ((pl.col("n_entries_used") - pl.col("n_translated")) / pl.col("n_entries_used") * 100).alias("pct_deficit"),
        )
        .filter(pl.col("n_entries_used") >= min_products // 5)  # pays-langue avec assez d'usage
        .sort("pct_deficit", descending=True)
    )
    return out


# ---------------------------------------------------------------------------
# D1. Catégories mortes (taxonomie -> jamais utilisée)
# ---------------------------------------------------------------------------

def dead_entries(
    products: pl.LazyFrame,
    entries: pl.DataFrame,
    tag_col: str,
) -> pl.DataFrame:
    """D1 — entrées de la taxonomie *jamais* utilisées par aucun produit.

    Inverse symétrique de :func:`unknown_tags`. Sert à signaler les entrées
    candidates à un nettoyage (vraies obsolètes) ou à un audit (trop
    spécifiques pour avoir des produits).
    """
    used_ids = (
        products.select(tag_col)
        .filter(pl.col(tag_col).is_not_null())
        .explode(tag_col)
        .filter(pl.col(tag_col).is_not_null())
        .unique()
        .rename({tag_col: "id"})
        .collect()
    )
    used_set = set(used_ids["id"].to_list())
    return (
        entries.filter(~pl.col("id").is_in(list(used_set)))
        .select("id", "taxonomy", "n_languages", "has_wikidata", "is_protected_name", "n_children", "n_parents")
        .sort("n_languages", descending=True)
    )


def used_entries_summary(
    products: pl.LazyFrame,
    entries: pl.DataFrame,
    tag_col: str,
) -> dict:
    """Résumé n_used / n_unused / pct_used + stat sur les produits par entrée."""
    used_counts = (
        products.select(tag_col)
        .filter(pl.col(tag_col).is_not_null())
        .explode(tag_col)
        .filter(pl.col(tag_col).is_not_null())
        .group_by(tag_col)
        .len()
        .rename({tag_col: "id", "len": "n_products"})
        .collect()
    )
    canonical_ids = set(entries["id"].to_list())
    used_canonical = used_counts.filter(pl.col("id").is_in(list(canonical_ids)))
    n_used = used_canonical.height
    n_total = entries.height
    return {
        "n_total": n_total,
        "n_used": n_used,
        "n_unused": n_total - n_used,
        "pct_used": n_used / n_total * 100 if n_total else 0.0,
        "median_products_per_entry": float(used_canonical["n_products"].median() or 0),
        "top_used_id": used_canonical.sort("n_products", descending=True).head(1)["id"].item() if n_used else None,
    }


# ---------------------------------------------------------------------------
# D2. Tags inconnus (produit -> tag absent de la taxonomie)
# ---------------------------------------------------------------------------

def unknown_tags(
    products: pl.LazyFrame,
    entries: pl.DataFrame,
    tag_col: str,
    top_n: int = 100,
    country_filter: list[str] | None = None,
) -> pl.DataFrame:
    """Top des tags présents dans les produits mais absents de la taxonomie.

    Returns: tag, lang_prefix, n_occurrences, n_countries, top_country
    """
    canonical_ids = set(entries["id"].to_list())
    tags = explode_tags(products, tag_col, country_filter=country_filter).collect()
    unknown = tags.filter(~pl.col("tag").is_in(canonical_ids))

    agg = (
        unknown.group_by("tag")
        .agg(
            pl.col("code").n_unique().alias("n_occurrences"),
            pl.col("country").n_unique().alias("n_countries"),
            pl.col("country").mode().first().alias("top_country"),
        )
        .with_columns(
            pl.col("tag").str.split(":").list.first().alias("lang_prefix"),
        )
        .sort("n_occurrences", descending=True)
        .head(top_n)
    )
    return agg


def unknown_tags_by_country(
    products: pl.LazyFrame,
    entries: pl.DataFrame,
    tag_col: str,
    country: str,
    top_n: int = 30,
) -> pl.DataFrame:
    """Top tags inconnus pour un pays spécifique."""
    canonical_ids = set(entries["id"].to_list())
    tags = explode_tags(products, tag_col).filter(pl.col("country") == country).collect()
    return (
        tags.filter(~pl.col("tag").is_in(canonical_ids))
        .group_by("tag")
        .agg(pl.col("code").n_unique().alias("n_products"))
        .sort("n_products", descending=True)
        .head(top_n)
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Mapping minimal pays_tag OFF -> codes langues officielles.
# Couvre les principaux pays utilisateurs d'OFF. Extensible.
COUNTRY_LANGUAGES: dict[str, list[str]] = {
    "en:france": ["fr"],
    "en:belgium": ["fr", "nl", "de"],
    "en:switzerland": ["fr", "de", "it", "rm"],
    "en:germany": ["de"],
    "en:austria": ["de"],
    "en:luxembourg": ["fr", "de", "lb"],
    "en:united-kingdom": ["en"],
    "en:ireland": ["en", "ga"],
    "en:united-states": ["en", "es"],
    "en:canada": ["en", "fr"],
    "en:spain": ["es", "ca", "gl", "eu"],
    "en:portugal": ["pt"],
    "en:italy": ["it"],
    "en:netherlands": ["nl"],
    "en:denmark": ["da"],
    "en:sweden": ["sv"],
    "en:norway": ["no", "nb", "nn"],
    "en:finland": ["fi", "sv"],
    "en:poland": ["pl"],
    "en:czech-republic": ["cs"],
    "en:hungary": ["hu"],
    "en:romania": ["ro"],
    "en:greece": ["el"],
    "en:croatia": ["hr"],
    "en:slovenia": ["sl"],
    "en:slovakia": ["sk"],
    "en:bulgaria": ["bg"],
    "en:russia": ["ru"],
    "en:ukraine": ["uk"],
    "en:turkey": ["tr"],
    "en:china": ["zh"],
    "en:japan": ["ja"],
    "en:south-korea": ["ko"],
    "en:india": ["hi", "en"],
    "en:brazil": ["pt"],
    "en:mexico": ["es"],
    "en:argentina": ["es"],
    "en:morocco": ["ar", "fr"],
    "en:algeria": ["ar", "fr"],
    "en:tunisia": ["ar", "fr"],
    "en:senegal": ["fr"],
    "en:ivory-coast": ["fr"],
    "en:cameroon": ["fr", "en"],
    "en:reunion": ["fr"],
    "en:guadeloupe": ["fr"],
    "en:martinique": ["fr"],
    "en:australia": ["en"],
    "en:new-zealand": ["en"],
}


def country_tag_to_iso(country_tag: str) -> str | None:
    """`en:france` -> 'FR' via pycountry. Fragile mais utile pour les cartes."""
    try:
        import pycountry
    except ImportError:
        return None
    if ":" not in country_tag:
        return None
    name = country_tag.split(":", 1)[1].replace("-", " ")
    try:
        c = pycountry.countries.lookup(name)
        return c.alpha_3
    except LookupError:
        # quelques exceptions OFF
        aliases = {
            "united kingdom": "GBR",
            "united states": "USA",
            "south korea": "KOR",
            "north korea": "PRK",
            "ivory coast": "CIV",
            "czech republic": "CZE",
            "reunion": "REU",
            "guadeloupe": "GLP",
            "martinique": "MTQ",
        }
        return aliases.get(name)
