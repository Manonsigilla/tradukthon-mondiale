-- ============================================================================
-- D2. Top candidats à ajouter à la taxonomie
-- ============================================================================
-- IMPORTANT: cette requête nécessite la taxonomie en table secondaire.
-- Upload `data/exports/taxonomy_categories.csv` dans Superset comme dataset
-- "taxonomy_categories" (colonnes: id), puis lance cette requête.
--
-- Sans la taxonomie, on peut approximer un "tag inconnu" comme un tag dont le
-- préfixe langue est inhabituel ou dont la valeur n'est pas une entrée connue.
-- Ici on utilise un anti-join propre :
--   tags présents sur des produits MAIS absents de la table taxonomy.
--
-- Viz Superset : Bar Chart trié décroissant + filtre Pays.
-- ============================================================================

WITH used AS (
    SELECT
        code,
        unnest(countries_tags)  AS country,
        unnest(categories_tags) AS tag
    FROM products
    WHERE categories_tags IS NOT NULL
      AND countries_tags  IS NOT NULL
),
unknown AS (
    SELECT
        u.country,
        u.tag,
        regexp_extract(u.tag, '^([a-z]{2,3}):', 1) AS lang_prefix,
        count(DISTINCT u.code)                    AS n_products
    FROM used u
    LEFT JOIN taxonomy_categories t ON t.id = u.tag
    WHERE t.id IS NULL                  -- tag absent de la taxonomie
      AND u.country IS NOT NULL
      AND u.tag    IS NOT NULL
    GROUP BY u.country, u.tag, lang_prefix
)
SELECT
    tag,
    lang_prefix,
    sum(n_products) AS n_products_global,
    count(DISTINCT country) AS n_countries
FROM unknown
GROUP BY tag, lang_prefix
ORDER BY n_products_global DESC
LIMIT 50;
