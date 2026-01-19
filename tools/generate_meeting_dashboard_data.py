#!/usr/bin/env python3
"""
Generate a compact JSON payload for the meeting dashboard.

Inputs:
  - research/delegator-band-timeseries.json (full monthly time series + latest snapshot)

Outputs:
  - static/data/meeting-dashboard.json (small, web-friendly)

Why this exists:
  - Keeps the meeting dashboard fast and offline-friendly (no external APIs / CDNs).
  - Avoids serving the full 600KB+ research dataset in the browser.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


def _compact_snapshot(snapshot: Dict[str, Any], *, top_n: int) -> Dict[str, Any]:
    conc = snapshot.get("concentration", {})
    delegators = dict(conc.get("delegators", {}))
    delegates = dict(conc.get("delegates", {}))

    if isinstance(delegators.get("top_delegators"), list):
        delegators["top_delegators"] = delegators["top_delegators"][:top_n]
    if isinstance(delegates.get("top_delegates"), list):
        delegates["top_delegates"] = delegates["top_delegates"][:top_n]

    return {
        "label": snapshot["label"],
        "snapshot_iso": snapshot["snapshot_iso"],
        "snapshot_block": snapshot["snapshot_block"],
        "active_delegators": snapshot["active_delegators"],
        "total_bonded_lpt": snapshot["total_bonded_lpt"],
        "bands": snapshot.get("bands", {}),
        "thresholds": snapshot.get("thresholds", {}),
        "concentration": {
            "delegators": delegators,
            "delegates": delegates,
        },
    }


def _compact_series(full: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in full.get("snapshots", []):
        c = s.get("concentration", {})
        out.append(
            {
                "label": s.get("label"),
                "snapshot_iso": s.get("snapshot_iso"),
                "active_delegators": s.get("active_delegators"),
                "total_bonded_lpt": s.get("total_bonded_lpt"),
                "delegates_active": c.get("delegates", {}).get("active_delegates"),
                "delegates_top10_share": c.get("delegates", {}).get("top_share", {}).get("10"),
                "delegators_top10_share": c.get("delegators", {}).get("top_share", {}).get("10"),
                "nakamoto_33": c.get("delegates", {}).get("nakamoto", {}).get("33%"),
                "nakamoto_50": c.get("delegates", {}).get("nakamoto", {}).get("50%"),
                "delegates_ge_100k": c.get("delegates", {}).get("delegates_ge_100k"),
                "delegates_ge_1m": c.get("delegates", {}).get("delegates_ge_1m"),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate meeting dashboard JSON payload.")
    parser.add_argument(
        "--input",
        default="research/delegator-band-timeseries.json",
        help="Path to the full time-series JSON.",
    )
    parser.add_argument(
        "--output",
        default="static/data/meeting-dashboard.json",
        help="Path to write the compact meeting payload.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=15,
        help="Number of top delegates/delegators to keep in the payload.",
    )
    args = parser.parse_args()

    full = _read_json(args.input)
    snapshots = full.get("snapshots", [])
    if not isinstance(snapshots, list) or not snapshots:
        raise SystemExit(f"no snapshots found in input: {args.input}")

    latest = snapshots[-1]
    payload = {
        "generated_at_utc": _utc_now_iso(),
        "source_generated_at_utc": full.get("generated_at_utc"),
        "source_path": args.input,
        "latest": _compact_snapshot(latest, top_n=max(1, int(args.top_n))),
        "series": _compact_series(full),
    }
    _write_json_atomic(args.output, payload)
    print(f"Wrote {args.output} ({len(json.dumps(payload))} bytes)")


if __name__ == "__main__":
    main()

