#!/usr/bin/env python3
"""
Build pre_orders_bundle.json (schema v2: columnar + dictionary-encoded).

Usage:
    # From the repo root (where data/ and new_data/ live):
    python3 scripts/build_pre_orders_bundle.py

Output:
    pre_orders_bundle.json (~18 MB, ~5-7 MB gzipped over the wire)

When to run:
    Every time you add new chunks to data/ or new_data/. The dashboard
    auto-invalidates its IndexedDB cache when the bundle's `n` field changes.

Schema v2 layout:
    {
      "v": 2,
      "n": <total row count>,
      "k": { "order_id":"i", "order_date":"d", ... },   # long → short key map
      "dicts": { "i":[...vocab], "d":[...], "s":[...], ... },  # string field dictionaries
      "idx":   { "i":[index_per_row,...], "d":[...], ... },     # int indices into dicts
      "num":   { "a":[29.24,...], "q":[4,...] }                 # raw number arrays
    }
"""

import json
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # adjust if script lives elsewhere

MANIFESTS = [
    REPO_ROOT / "data" / "manifest.json",
    REPO_ROOT / "new_data" / "manifest.json",
]

# Long-name → short-key map (dashboard inverts on load)
KEY_MAP = OrderedDict([
    ("order_id",           "i"),
    ("order_date",         "d"),
    ("amount_usd",         "a"),
    ("qty",                "q"),
    ("sku",                "s"),
    ("region",             "r"),
    ("country",            "c"),
    ("promotion_category", "p"),
])
DICT_FIELDS = ["i", "d", "s", "r", "c", "p"]   # high-repetition string fields → dictionary
NUM_FIELDS  = ["a", "q"]                          # numeric → raw arrays


def main() -> int:
    out_path = REPO_ROOT / "pre_orders_bundle.json"

    # ── Pass 1: read every chunk and accumulate slim rows ─────────────────
    slim_rows: list[dict] = []
    for mf_path in MANIFESTS:
        if not mf_path.exists():
            print(f"  ⚠ manifest missing: {mf_path}", file=sys.stderr)
            continue
        with mf_path.open(encoding="utf-8") as f:
            manifest = json.load(f)
        print(f"  {mf_path.relative_to(REPO_ROOT)}: {manifest['total_records']:,} rows / {manifest['total_chunks']} chunks")
        for rel_path in manifest["files"]:
            chunk_path = REPO_ROOT / rel_path
            if not chunk_path.exists():
                print(f"    ⚠ chunk missing: {chunk_path}", file=sys.stderr)
                continue
            with chunk_path.open(encoding="utf-8") as f:
                rows = json.load(f)
            for r in rows:
                slim_rows.append({short: r.get(long) for long, short in KEY_MAP.items()})

    if not slim_rows:
        print("✗ No rows collected — check that data/ and new_data/ exist.", file=sys.stderr)
        return 1

    N = len(slim_rows)
    print(f"\n  → {N:,} total rows")

    # ── Pass 2: build dictionaries + per-row index arrays ─────────────────
    dicts: dict = {}
    idx_cols: dict = {}
    for fld in DICT_FIELDS:
        seen: dict = {}
        vocab: list = []
        indices = [-1] * N
        for i, r in enumerate(slim_rows):
            v = r.get(fld)
            if v is None:
                continue
            ix = seen.get(v)
            if ix is None:
                ix = len(vocab)
                seen[v] = ix
                vocab.append(v)
            indices[i] = ix
        dicts[fld] = vocab
        idx_cols[fld] = indices
        print(f"    {fld}: dict size {len(vocab):,}")

    # Number columns: raw arrays, None for missing
    num_cols = {
        fld: [r.get(fld) for r in slim_rows]
        for fld in NUM_FIELDS
    }

    bundle = OrderedDict([
        ("v",     2),
        ("n",     N),
        ("k",     KEY_MAP),
        ("dicts", dicts),
        ("idx",   idx_cols),
        ("num",   num_cols),
    ])

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, separators=(",", ":"), ensure_ascii=False)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\n✓ wrote {out_path.relative_to(REPO_ROOT)}  ({N:,} rows, {size_mb:.1f} MB)")
    if size_mb > 95:
        print(f"  ⚠ approaching GitHub 100 MB hard limit — consider further slimming.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
