# OFF Taxonomy Coverage

Mesurer la **couverture** et la **complétude** des taxonomies Open Food Facts
**par pays** et **par langue**, à partir des exports publics OFF.

## Le rapport

Un site Quarto multi-pages en `_site/` :

| Page                                    | Contenu                                                          |
| --------------------------------------- | ---------------------------------------------------------------- |
| [`index`](report/index.qmd)             | Pitch, sources, comment reproduire                               |
| [`01-taxonomy`](report/01-taxonomy.qmd) | Stats brutes des taxonomies : entrées, langues, hiérarchie       |
| [`02-coverage`](report/02-coverage.qmd) | Couverture taxonomique par pays — cartes choroplèthes mondiales  |
| [`03-gaps`](report/03-gaps.qmd)         | **Déficit pays × langue** (heatmap) + tags inconnus à ajouter    |

## 4 métriques

- **A — Couverture pays** : % de tags catégories/ingrédients canoniques, par pays
- **B — Complétude multilingue** : combien de langues couvre chaque entrée
- **C — Déficit pays × langue** : pour chaque langue *officielle* d'un pays,
  % d'entrées effectivement utilisées qui ne sont pas traduites dans cette langue
- **D — Tags inconnus** : tags utilisés par les contributeurs mais absents
  de la taxonomie ; priorisés par fréquence

## Quelques chiffres clés

- **14 437** catégories, **6 013** ingrédients — couvrant **238** langues
- **4,1** langues / catégorie (médiane = 2) ; **14** langues / ingrédient
- **France** = 1,2 M produits (96,7 % de tags catégorie canoniques) ;
  **États-Unis** = 909 K (92,9 %)
- 🚨 **Suisse / Romanche** : 99,96 % de déficit (2 entrées traduites sur 4 538)
- 🚨 **Luxembourg / Luxembourgeois** : 99,3 % de déficit
- Top tag inconnu : `en:groceries` — 66 499 produits dans 171 pays

## Reproduire

```bash
pip install -e .
python scripts/download_data.py    # taxonomies + parquet OFF (~7 Go)
quarto render
```

## Stack

- **Python 3.11+**, **Polars 1.x** (lecture lazy du parquet 7 Go, projection des
  6 colonnes utiles → tout tient en ~3 s pour la couverture pays)
- **Quarto** site multi-pages
- **Plotly** pour les choroplèthes et heatmaps interactives
- **pycountry** pour le mapping `en:france` → `FRA` (ISO-3)

## Structure

```text
.
├── pyproject.toml
├── _quarto.yml
├── scripts/
│   └── download_data.py    # idempotent, taxonomies + parquet
├── src/
│   ├── taxonomy.py         # parser JSON OFF
│   ├── loader.py           # scan_parquet lazy + projection
│   └── metrics.py          # 4 métriques A/B/C/D + mapping pays-langues
├── report/
│   ├── index.qmd
│   ├── 01-taxonomy.qmd
│   ├── 02-coverage.qmd
│   └── 03-gaps.qmd
└── data/raw/               # téléchargé, gitignored
    ├── categories.full.json
    ├── ingredients.full.json
    └── food.parquet
```

## Sources OFF

- Taxonomies : <https://static.openfoodfacts.org/data/taxonomies/>
- Parquet produits : <https://huggingface.co/datasets/openfoodfacts/product-database>
