#!/usr/bin/env python3
"""
Build pre_orders_bundle.json by reading all chunk files from the data/ and
new_data/ folders and combining them into a single slimmed JSON bundle.

Usage:
    # From the repo root (where data/ and new_data/ live):
    python3 scripts/build_pre_orders_bundle.py

Output:
    pre_orders_bundle.json (~50 MB, ~12 MB gzipped over the wire)

When to run:
    Every time you add new chunks to data/ or new_data/ (e.g., after the
    insert_new_orders.yml workflow finishes). The dashboard automatically
    cache-invalidates when the bundle's `n` field changes.

Optional: wire this into a GitHub Actions workflow that runs on push to
main when chunk files change, and commits the regenerated bundle back.
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # adjust if script lives elsewhere

MANIFESTS = [
    REPO_ROOT / "data" / "manifest.json",
    REPO_ROOT / "new_data" / "manifest.json",
]

# Only these 8 fields are actually used by the dashboard (fillCompareKpis).
# The other ~32 fields per row are dropped — saves ~80% on size and memory.
KEY_MAP = {
    "order_id":           "i",
    "order_date":         "d",
    "amount_usd":         "a",
    "qty":                "q",
    "sku":                "s",
    "region":             "r",
    "country":            "c",
    "promotion_category": "p",
}
FIELDS = list(KEY_MAP.keys())


def main() -> int:
    out_path = REPO_ROOT / "pre_orders_bundle.json"
    all_rows: list[dict] = []

    for mf_path in MANIFESTS:
        if not mf_path.exists():
            print(f"  ⚠ manifest missing: {mf_path}", file=sys.stderr)
            continue
        with mf_path.open(encoding="utf-8") as f:
            manifest = json.load(f)
        folder = mf_path.parent
        print(f"  {mf_path.relative_to(REPO_ROOT)}: {manifest['total_records']:,} rows / {manifest['total_chunks']} chunks")
        for rel_path in manifest["files"]:
            chunk_path = REPO_ROOT / rel_path
            if not chunk_path.exists():
                print(f"    ⚠ chunk missing: {chunk_path}", file=sys.stderr)
                continue
            with chunk_path.open(encoding="utf-8") as f:
                rows = json.load(f)
            for r in rows:
                slim = {KEY_MAP[f]: r.get(f) for f in FIELDS if r.get(f) is not None}
                all_rows.append(slim)

    if not all_rows:
        print("✗ No rows collected — check that data/ and new_data/ exist.", file=sys.stderr)
        return 1

    bundle = {
        "v": 1,                 # schema version
        "k": KEY_MAP,           # long → short key map (dashboard inverts on load)
        "n": len(all_rows),     # total record count (cache-invalidation key)
        "rows": all_rows,
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, separators=(",", ":"), ensure_ascii=False)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"✓ wrote {out_path.relative_to(REPO_ROOT)}  ({len(all_rows):,} rows, {size_mb:.1f} MB)")
    if size_mb > 95:
        print(f"  ⚠ Approaching GitHub 100 MB hard limit. Consider splitting or further slimming.", file=sys.stderr)
    elif size_mb > 48:
        print(f"  ⓘ Above 50 MB → GitHub will show a 'large file' warning on commit (still allowed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
