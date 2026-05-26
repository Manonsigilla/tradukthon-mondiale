-- ============================================================================
-- D2. Top candidats à ajouter à la taxonomie
-- ============================================================================
-- IMPORTANT: cette requête nécessite la taxonomie en table secondaire.
-- Upload `data/exports/taxonomy_categories.csv` dans Superset comme dataset
-- "taxonomy_categories" (colonnes: id), puis lance cette requête.
--
-- Logique :
--   1. exploser produits × pays × tags
--   2. anti-join sur la taxonomie (LEFT JOIN ... WHERE t.id IS NULL)
--   3. agréger par tag : un produit n'est compté qu'une fois même s'il est
--      vendu dans plusieurs pays (count DISTINCT code)
--
-- Viz Superset : Bar Chart trié décroissant + filtre Pays.
-- ============================================================================

WITH used AS (
    SELECT
        code,
        unnest(countries_tags)  AS country,
        unnest(categories_tags) AS tag
    FROM food_products
    WHERE categories_tags IS NOT NULL
      AND countries_tags  IS NOT NULL
)
SELECT
    u.tag,
    regexp_extract(u.tag, '^([a-z]{2,3}):', 1) AS lang_prefix,
    count(DISTINCT u.code)                     AS n_products,
    count(DISTINCT u.country)                  AS n_countries
FROM used u
LEFT JOIN taxonomy_categories t ON t.id = u.tag
WHERE t.id IS NULL                  -- tag absent de la taxonomie
  AND u.tag IS NOT NULL
GROUP BY u.tag, lang_prefix
ORDER BY n_products DESC
LIMIT 50;
