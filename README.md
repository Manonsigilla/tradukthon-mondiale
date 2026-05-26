# OFF Taxonomy Coverage

Mesurer la **couverture** et la **complétude** des taxonomies Open Food Facts
**par pays** et **par langue**, à partir des exports publics OFF.

Bonus : un **bridge vers Superset** (sql.openfoodfacts.org) qui transpose les
mêmes métriques en SQL DuckDB pour les contributeurs non-techniques.

## Le rapport

Un site Quarto multi-pages en `_site/` :

| Page                                    | Contenu                                                              |
| --------------------------------------- | -------------------------------------------------------------------- |
| [`index`](report/index.qmd)             | Pitch, sources, grille A/B/C/D                                       |
| [`01-taxonomy`](report/01-taxonomy.qmd) | **A** : la taxonomie elle-même — entrées, langues, complétude        |
| [`02-coverage`](report/02-coverage.qmd) | **B1/B2** : couverture des produits par pays — cartes choroplèthes   |
| [`03-gaps`](report/03-gaps.qmd)         | **C/D1/D2** : déficit pays × langue, cat. mortes, tags à ajouter     |
| [`04-superset`](report/04-superset.qmd) | Bridge vers Superset + 6 requêtes SQL DuckDB prêtes à l'emploi       |

## 6 métriques

- **A — Complétude de la taxonomie elle-même** : pour chaque langue, % d'entrées
  canoniques traduites
- **B1 — Taux d'étiquetage par pays** : % de produits ayant au moins une `categories_tag`
- **B2 — Qualité des tags** : parmi les produits étiquetés, % de tags canoniques
  (dans la taxonomie)
- **C — Déficit pays × langue** : pour chaque langue *officielle* d'un pays,
  % d'entrées effectivement utilisées qui ne sont pas traduites dans cette langue
- **D1 — Catégories mortes** : entrées de taxonomie jamais utilisées par aucun produit
- **D2 — Tags inconnus** : tags utilisés par les contributeurs mais absents
  de la taxonomie ; priorisés par fréquence

## Quelques chiffres clés

- **14 437** catégories, **6 013** ingrédients — couvrant **238** langues
- **4,1** langues / catégorie en moyenne ; **14** langues / ingrédient
- **France** = 1,2 M produits (96,7 % de tags catégorie canoniques)
- 🚨 **Suisse / Romanche** : 99,96 % de déficit (2 entrées traduites sur 4 538)
- 🚨 **Luxembourg / Luxembourgeois** : 99,3 % de déficit
- 🚨 **Japon** : 8 % seulement des produits étiquetés
- 🚨 **5 005 catégories sur 14 437 (34 %) jamais utilisées** par aucun produit
- Top tag inconnu : `en:groceries` — 66 499 produits dans 171 pays

## Reproduire de zéro

```bash
pip install -e .

# 1. Télécharger les sources OFF (~7 Go au total, peut prendre plusieurs minutes)
python scripts/download_data.py

# 2. Pré-calculer toutes les métriques (cache parquet, ~30s à 2 min selon la machine)
python scripts/precompute.py

# 3. (Optionnel) générer les CSV à uploader dans Superset
python scripts/export_for_superset.py

# 4. Rendre le site Quarto
quarto render
quarto preview          # serveur local + auto-reload
```

⚠️ **L'étape 2 (`precompute.py`) est obligatoire** — les pages Quarto lisent
des fichiers `data/cache/*.parquet` qu'elle produit. Sans cache, le render
plante (ou prend des heures à recalculer dans le kernel Jupyter).

## Stack

- **Python 3.11+**, **Polars 1.x** (lecture lazy du parquet 7 Go, projection des
  6 colonnes utiles → couverture pays calculée en ~3 s)
- **Quarto** site multi-pages (light + dark mode)
- **Plotly** pour les choroplèthes, heatmaps, et menu déroulant interactif
- **pycountry** pour le mapping `en:france` → `FRA` (ISO-3)
- **DuckDB** côté Superset (requêtes prêtes dans `sql/`)

## Structure

```text
.
├── pyproject.toml
├── _quarto.yml             # thème light/dark, navbar
├── custom-light.scss       # palette claire
├── custom-dark.scss        # palette sombre
├── scripts/
│   ├── download_data.py    # idempotent, taxonomies + parquet
│   ├── precompute.py       # calcule toutes les métriques → data/cache/
│   └── export_for_superset.py  # → data/exports/*.csv
├── src/
│   ├── taxonomy.py         # parser JSON OFF
│   ├── loader.py           # scan_parquet lazy + projection
│   └── metrics.py          # 6 métriques + mapping pays-langues
├── sql/                    # 6 requêtes DuckDB pour Superset
│   ├── 01_b1_labeling_rate.sql
│   ├── 02_top_categories_by_country.sql
│   ├── 03_d2_unknown_tag_candidates.sql
│   ├── 04_c_deficit_country_language.sql
│   ├── 05_global_completeness_kpi.sql
│   └── 06_b1_nutriscore_bonus.sql
├── report/
│   ├── index.qmd
│   ├── 01-taxonomy.qmd
│   ├── 02-coverage.qmd
│   ├── 03-gaps.qmd
│   └── 04-superset.qmd
└── data/                   # tout gitignored
    ├── raw/                # téléchargé
    │   ├── categories.full.json
    │   ├── ingredients.full.json
    │   └── food.parquet
    ├── cache/              # produit par precompute.py
    └── exports/            # produit par export_for_superset.py
```

## Sources OFF

- Taxonomies : <https://static.openfoodfacts.org/data/taxonomies/>
- Parquet produits : <https://huggingface.co/datasets/openfoodfacts/product-database>
- BI Superset OFF : <https://sql.openfoodfacts.org>
- Wiki DuckDB OFF : <https://wiki.openfoodfacts.org/DuckDB_Cheatsheet>
