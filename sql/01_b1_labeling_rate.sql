-- ============================================================================
-- B1. Taux d'étiquetage des produits par pays
-- ============================================================================
-- À coller dans sql.openfoodfacts.org (DuckDB).
-- Aucune dépendance externe : tourne sur le parquet OFF tel quel.
--
-- Pour chaque pays, calcule:
--   - n_products_total      = nombre total de produits associés au pays
--   - n_products_tagged     = combien ont au moins une categories_tag
--   - pct_tagged            = ratio en %
--
-- Viz Superset recommandée : Choropleth Map (ou Bar Chart top/flop).
-- ============================================================================

WITH exploded AS (
    SELECT
        code,
        unnest(countries_tags) AS country,
        (categories_tags IS NOT NULL AND len(categories_tags) > 0) AS has_category
    FROM food_products
    WHERE countries_tags IS NOT NULL
),
agg AS (
    SELECT
        country,
        count(DISTINCT code)                                AS n_products_total,
        count(DISTINCT CASE WHEN has_category THEN code END) AS n_products_tagged
    FROM exploded
    WHERE country IS NOT NULL
    GROUP BY country
)
SELECT
    country,
    n_products_total,
    n_products_tagged,
    round(100.0 * n_products_tagged / n_products_total, 2) AS pct_tagged
FROM agg
WHERE n_products_total >= 200
ORDER BY n_products_total DESC;
