-- ============================================================================
-- Top catégories utilisées par pays
-- ============================================================================
-- Sert de base à la métrique C (déficit de traduction) côté Superset.
-- Pour un pays donné (paramétrable via Superset filter), liste les catégories
-- les plus fréquentes — celles qui demandent en priorité une traduction.
--
-- Aucune dépendance externe.
--
-- Viz Superset recommandée : Table interactive + filtre "Pays".
-- ============================================================================

WITH exploded AS (
    SELECT
        code,
        unnest(countries_tags)  AS country,
        unnest(categories_tags) AS category_tag
    FROM food_products
    WHERE countries_tags IS NOT NULL
      AND categories_tags IS NOT NULL
),
ranked AS (
    SELECT
        country,
        category_tag,
        count(DISTINCT code)                                       AS n_products,
        regexp_extract(category_tag, '^([a-z]{2,3}):', 1)          AS tag_lang_prefix
    FROM exploded
    WHERE country IS NOT NULL AND category_tag IS NOT NULL
    GROUP BY country, category_tag
)
SELECT
    country,
    category_tag,
    tag_lang_prefix,
    n_products
FROM ranked
WHERE country IN (
    'en:france', 'en:united-states', 'en:germany', 'en:spain',
    'en:italy', 'en:united-kingdom', 'en:belgium', 'en:switzerland',
    'en:netherlands', 'en:poland'
)
ORDER BY country, n_products DESC;
