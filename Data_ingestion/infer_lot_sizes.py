# Data_ingestion/infer_lot_sizes.py
"""Derives a lot-size reference table directly from the ingested option
data instead of hardcoding one. NSE lot sizes are revised roughly every
quarter (based on average contract value over the preceding months), so a
hardcoded table goes stale fast and there's no live Zerodha session
required to source it here -- every real trade's volume must be an exact
multiple of the contract's lot size, so the lot size is just the GCD of
observed non-zero traded volumes for that underlying (verified on
ICICIBANK during the Phase 1 audit: inferred exactly 700, with every
sampled volume a clean multiple of it).

Only meaningful once options_ingest_stock.py / options_ingest_index.py
have populated historical_data_dir/options/ -- this reads their output,
it doesn't touch the raw source archives at all.

Caveat for the "index" category (NIFTY/BANKNIFTY): this GCD trick is only
as good as the volume field it's built on. Verified reliable for stocks
(ICICIBANK inferred exactly 700, every sampled volume a clean multiple) --
but options_ingest_index.py's own docstring already flags that the index
tick data's "volume" field has unresolved semantics (looks cumulative most
of the day but shows real decreases late in the day, which cumulative
volume can't do). A test run here produced NIFTY=5 and BANKNIFTY=30, both
suspiciously small next to NSE's real historical lot sizes for these
indices -- read as "GCD of a noisy/ambiguous field", not a trustworthy lot
size. Only 2-6 indices exist (vs 200+ stocks), so the better fix is a
direct lookup (Kite's own instruments dump carries a real lot_size field
per contract) rather than leaning on inference here -- treat this
function's index-category output as a low-confidence placeholder only.
"""

import math
import os
from dataclasses import dataclass
from functools import reduce
from typing import List, Optional

import polars as pl
from collections import Counter

from infrastructure.config.settings import get_settings

SAMPLE_FILES_PER_UNDERLYING = 25
SAMPLE_EXPIRIES_PER_UNDERLYING = 6
MIN_VOLUMES_PER_FILE = 5  # a file with only a couple of trades is too noisy to trust its own GCD


@dataclass
class LotSizeEstimate:
    underlying: str
    lot_size: Optional[int]
    sample_volumes: int
    files_sampled: int


def _infer_for_underlying(underlying_dir: str) -> LotSizeEstimate:
    """GCD-of-volumes as a single pooled computation is fragile: one file
    with a single odd/contaminated volume value drags the WHOLE estimate
    down (verified -- ADANIENT came out as lot_size=3 that way, when the
    real value is 309). Instead, take the GCD *per file*, then use the
    most common per-file GCD as the estimate -- one bad file just becomes
    a minority outlier instead of poisoning the result (verified: recovers
    ADANIENT=309 and KOTAKBANK=400, both realistic NSE lot sizes, while
    leaving already-correct cases like PAGEIND=15 unchanged)."""
    underlying = os.path.basename(underlying_dir)
    expiries = sorted(os.listdir(underlying_dir))[-SAMPLE_EXPIRIES_PER_UNDERLYING:]

    per_file_gcds: List[int] = []
    total_volumes = 0
    files_sampled = 0
    for expiry in expiries:
        expiry_dir = os.path.join(underlying_dir, expiry)
        files = sorted(os.listdir(expiry_dir), key=lambda f: -os.path.getsize(os.path.join(expiry_dir, f)))
        for fname in files[:SAMPLE_FILES_PER_UNDERLYING]:
            df = pl.read_csv(os.path.join(expiry_dir, fname), columns=["volume"])
            nonzero = df.filter(pl.col("volume") > 0)["volume"].to_list()
            files_sampled += 1
            if len(nonzero) < MIN_VOLUMES_PER_FILE:
                continue
            total_volumes += len(nonzero)
            g = reduce(math.gcd, nonzero)
            if g > 0:
                per_file_gcds.append(g)

    if not per_file_gcds:
        return LotSizeEstimate(underlying, None, total_volumes, files_sampled)

    lot_size, _ = Counter(per_file_gcds).most_common(1)[0]
    return LotSizeEstimate(underlying, lot_size, total_volumes, files_sampled)


def infer_lot_sizes(options_root: Optional[str] = None) -> str:
    """options_root should contain subfolders like stocks/<UNDERLYING>/ and
    index/<UNDERLYING>/, each already produced by the ingest scripts."""
    options_root = options_root or os.path.join(get_settings().historical_data_dir, "options")

    rows = []
    for category in ("stocks", "index"):
        cat_dir = os.path.join(options_root, category)
        if not os.path.isdir(cat_dir):
            continue
        for name in sorted(os.listdir(cat_dir)):
            underlying_dir = os.path.join(cat_dir, name)
            if not os.path.isdir(underlying_dir):
                continue
            est = _infer_for_underlying(underlying_dir)
            rows.append(
                {
                    "category": category,
                    "underlying": est.underlying,
                    "inferred_lot_size": est.lot_size,
                    "sample_volume_count": est.sample_volumes,
                    "files_sampled": est.files_sampled,
                }
            )
            print(f"  {category}/{est.underlying}: lot_size={est.lot_size} "
                  f"(from {est.sample_volumes} volumes across {est.files_sampled} files)")

    out_df = pl.DataFrame(rows)
    out_path = os.path.join(options_root, "lot_sizes.csv")
    out_df.write_csv(out_path)
    print(f"\n{len(rows)} underlyings -> {out_path}")
    return out_path


if __name__ == "__main__":
    infer_lot_sizes()
