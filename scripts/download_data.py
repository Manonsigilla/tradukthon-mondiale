"""Télécharge les sources nécessaires au rapport (taxonomies + parquet OFF).

Usage:
    python scripts/download_data.py            # tout
    python scripts/download_data.py taxonomies # seulement les taxonomies
    python scripts/download_data.py parquet    # seulement le parquet (~2 Go)

Tous les fichiers sont placés sous data/raw/. Idempotent: ne re-télécharge pas
ce qui est déjà présent (sauf si --force).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

TAXONOMIES = {
    "categories.full.json": "https://static.openfoodfacts.org/data/taxonomies/categories.full.json",
    "ingredients.full.json": "https://static.openfoodfacts.org/data/taxonomies/ingredients.full.json",
}

PARQUET_URL = "https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet"
PARQUET_NAME = "food.parquet"


def download(url: str, dest: Path, force: bool = False) -> None:
    if dest.exists() and not force:
        print(f"[skip] {dest.name} déjà présent ({dest.stat().st_size / 1e6:.1f} Mo)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[get ] {url}")
    headers = {"User-Agent": "OFF-Taxonomy-Coverage/0.1 (hackathon; +https://openfoodfacts.org)"}
    with requests.get(url, stream=True, timeout=60, headers=headers) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 Mo
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"   {downloaded / 1e6:7.1f} / {total / 1e6:7.1f} Mo ({pct:5.1f}%)", end="\r")
    print(f"\n[ok  ] {dest} ({dest.stat().st_size / 1e6:.1f} Mo)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", nargs="?", default="all", choices=["all", "taxonomies", "parquet"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.target in ("all", "taxonomies"):
        for fname, url in TAXONOMIES.items():
            download(url, RAW_DIR / fname, force=args.force)

    if args.target in ("all", "parquet"):
        print("\n--- Parquet OFF (~2 Go, peut prendre plusieurs minutes) ---")
        download(PARQUET_URL, RAW_DIR / PARQUET_NAME, force=args.force)

    return 0


if __name__ == "__main__":
    sys.exit(main())
