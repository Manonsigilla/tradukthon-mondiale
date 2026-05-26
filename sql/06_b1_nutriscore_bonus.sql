-- ============================================================================
-- BONUS — Classement des pays par Nutri-Score moyen
-- ============================================================================
-- Pour répondre à l'exemple du brief ("classement des pays par Nutri-Score ?").
-- Pas central pour le récit "couverture", mais à inclure comme bonus pour
-- montrer la puissance combinée Quarto+Superset.
--
-- Viz Superset : Bar Chart trié + carte choroplèthe.
-- ============================================================================

WITH per_country AS (
    SELECT
        unnest(countries_tags)            AS country,
        upper(nutriscore_grade)           AS grade
    FROM products
    WHERE countries_tags  IS NOT NULL
      AND nutriscore_grade IN ('a','b','c','d','e')
)
SELECT
    country,
    count(*)                                                   AS n_products_scored,
    sum(CASE WHEN grade = 'A' THEN 1 ELSE 0 END)               AS n_a,
    sum(CASE WHEN grade = 'B' THEN 1 ELSE 0 END)               AS n_b,
    sum(CASE WHEN grade = 'C' THEN 1 ELSE 0 END)               AS n_c,
    sum(CASE WHEN grade = 'D' THEN 1 ELSE 0 END)               AS n_d,
    sum(CASE WHEN grade = 'E' THEN 1 ELSE 0 END)               AS n_e,
    -- score moyen pondéré : A=1, B=2, C=3, D=4, E=5 (plus bas = mieux)
    round(avg(CASE grade
        WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3
        WHEN 'D' THEN 4 WHEN 'E' THEN 5 END), 2)               AS avg_score,
    round(100.0 * sum(CASE WHEN grade IN ('A','B') THEN 1 ELSE 0 END) / count(*), 1)
                                                               AS pct_healthy
FROM per_country
GROUP BY country
HAVING count(*) >= 1000
ORDER BY avg_score ASC;
