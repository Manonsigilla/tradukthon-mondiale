-- ============================================================================
-- KPI global : "Score de complétude mondiale"
-- ============================================================================
-- Un seul chiffre à afficher en gros en haut du dashboard Superset.
--
-- Question : sur tous les produits OFF, quel % a une catégorie principale
-- qui peut être affichée *dans la langue du contributeur qui l'a saisi* ?
--
-- Nécessite : taxonomy_labels (id, lang) en dataset secondaire.
--
-- Viz Superset : Big Number (KPI tile).
-- ============================================================================

WITH first_category AS (
    -- on prend la première catégorie de chaque produit
    SELECT
        code,
        lang AS product_lang,
        categories_tags[1] AS main_category
    FROM products
    WHERE categories_tags IS NOT NULL
      AND len(categories_tags) > 0
      AND lang IS NOT NULL
),
labeled AS (
    SELECT
        f.code,
        f.product_lang,
        f.main_category,
        tl.id IS NOT NULL AS has_translation_in_product_lang
    FROM first_category f
    LEFT JOIN taxonomy_labels tl
        ON tl.id = f.main_category
       AND tl.lang = f.product_lang
)
SELECT
    count(*)                                              AS n_products_with_category,
    sum(CASE WHEN has_translation_in_product_lang THEN 1 ELSE 0 END) AS n_translated,
    round(100.0 *
          sum(CASE WHEN has_translation_in_product_lang THEN 1 ELSE 0 END) /
          count(*), 2)                                    AS global_completeness_pct
FROM labeled;
