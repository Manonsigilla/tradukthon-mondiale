# Quickstart

Comment lancer le projet sur une nouvelle machine, en partant d'un `git clone`.

## Prérequis

- **Python 3.11+**
- **Quarto 1.4+** — à télécharger sur <https://quarto.org/docs/get-started/>
- **~10 Go d'espace disque** (le parquet OFF fait ~7 Go)
- **~4 Go de RAM minimum** (8 Go recommandés pour le précompute)

## Étapes

```bash
# 1. Cloner et installer les deps Python
git clone <URL_DU_REPO>
cd <NOM_DU_REPO>
pip install -e .

# 2. Télécharger les sources OFF (long la première fois)
python scripts/download_data.py
# → data/raw/categories.full.json   (~7 Mo)
# → data/raw/ingredients.full.json  (~6 Mo)
# → data/raw/food.parquet           (~7 Go, peut prendre 10-30 min selon connexion)

# 3. Précalculer toutes les métriques (lit le parquet une seule fois)
python scripts/precompute.py
# → data/cache/*.parquet   (12 fichiers, ~3 Mo total, ~30s à 2 min)

# 4. (Optionnel) générer les CSV à uploader dans Superset
python scripts/export_for_superset.py
# → data/exports/taxonomy_categories.csv
# → data/exports/taxonomy_labels.csv
# → data/exports/country_languages.csv

# 5. Rendre le site
quarto render            # produit _site/
quarto preview           # serveur local avec auto-reload, ouvre le navigateur
```

## Vérifications rapides

Si une étape échoue, vérifier dans cet ordre :

| Symptôme | Cause probable | Fix |
|---|---|---|
| `quarto: command not found` | Quarto n'est pas installé / pas dans le PATH | Installer depuis quarto.org puis **rouvrir la fenêtre du terminal** |
| `ModuleNotFoundError: No module named 'src'` | Étape 1 oubliée | `pip install -e .` à la racine |
| `FileNotFoundError: data/raw/food.parquet` | Étape 2 oubliée | `python scripts/download_data.py` |
| `FileNotFoundError: data/cache/...` | Étape 3 oubliée | `python scripts/precompute.py` |
| Kernel Jupyter timeout >60s au render | Antivirus qui scanne ipykernel | Ajouter le dossier projet en exclusion de Windows Defender |
| `Segmentation fault` pendant le précompute | RAM insuffisante (ingrédients) | C'est attendu sur certains hardware — le script skippe ingrédients automatiquement, les catégories suffisent |

## Reproduire le précompute partiellement

Le script `precompute.py` est **idempotent** : il skippe les fichiers déjà présents
dans `data/cache/`. Pour forcer un recalcul total :

```bash
python scripts/precompute.py --force
```

Pour ne recalculer qu'une métrique, supprimer son fichier dans `data/cache/`
puis relancer.

## Publier sur GitHub Pages

```bash
quarto publish gh-pages
```

(Nécessite un repo GitHub accessible, et la première fois Quarto demandera
les credentials.)

## Workflow Superset

Une fois `data/exports/` rempli :

1. Aller sur <https://sql.openfoodfacts.org>
2. **Data → Datasets → + Dataset** pour chacun des 3 CSV de `data/exports/`
3. Coller les requêtes `sql/*.sql` dans SQL Lab et sauver en Charts
4. Assembler le dashboard

Détail complet dans [`report/04-superset.qmd`](report/04-superset.qmd).
