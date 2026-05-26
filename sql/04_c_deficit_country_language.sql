-- ============================================================================
-- C. Déficit de traduction pays × langue (la métrique star)
-- ============================================================================
-- Nécessite deux datasets secondaires dans Superset :
--   1. taxonomy_categories (id, taxonomy)   - cf. data/exports/taxonomy_categories.csv
--   2. taxonomy_labels     (id, lang)       - cf. data/exports/taxonomy_labels.csv
--   3. country_languages   (country, lang)  - cf. data/exports/country_languages.csv
--
-- Pour chaque (pays, langue officielle), compte:
--   - n_entries_used  : combien d'entrées de la taxonomie sont utilisées dans
--                       les produits vendus dans ce pays
--   - n_translated    : combien d'entre elles ont une traduction dans la langue
--   - pct_deficit     : (n_used - n_translated) / n_used * 100
--
-- Viz Superset : Heatmap (rows=country, cols=lang, value=pct_deficit).
-- ============================================================================

WITH used_in_country AS (
    SELECT DISTINCT
        unnest(countries_tags)  AS country,
        unnest(categories_tags) AS entry_id
    FROM products
    WHERE categories_tags IS NOT NULL
      AND countries_tags  IS NOT NULL
),
canonical_used AS (
    -- ne garder que les entrées vraiment dans la taxonomie
    SELECT u.country, u.entry_id
    FROM used_in_country u
    INNER JOIN taxonomy_categories t ON t.id = u.entry_id
    WHERE u.country IS NOT NULL AND u.entry_id IS NOT NULL
),
country_lang_pairs AS (
    -- pays × langues officielles
    SELECT cl.country, cl.lang
    FROM country_languages cl
),
joined AS (
    SELECT
        cu.country,
        clp.lang,
        cu.entry_id,
        tl.id IS NOT NULL AS has_translation
    FROM canonical_used cu
    INNER JOIN country_lang_pairs clp ON clp.country = cu.country
    LEFT JOIN taxonomy_labels tl
        ON tl.id = cu.entry_id AND tl.lang = clp.lang
)
SELECT
    country,
    lang,
    count(DISTINCT entry_id)                                         AS n_entries_used,
    count(DISTINCT CASE WHEN has_translation THEN entry_id END)      AS n_translated,
    round(
        100.0 * (count(DISTINCT entry_id) - count(DISTINCT CASE WHEN has_translation THEN entry_id END))
        / count(DISTINCT entry_id), 2
    ) AS pct_deficit
FROM joined
GROUP BY country, lang
HAVING count(DISTINCT entry_id) >= 100
ORDER BY pct_deficit DESC;
