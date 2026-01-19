#!/usr/bin/env python3
"""
Livepeer delegation "board" report (Arbitrum).

Combines:
- Current delegator bracket distribution (counts + bonded LPT)
- Net changes over a chosen window (counts + bonded)
- Inflow proxy: new delegators per year by max-bonded band (from outflow report)
- Outflow proxy: withdrawers + withdrawn LPT by max-bonded band (from outflow report)
- Delegate (orchestrator) gain/bleed: net stake change between snapshots, using
  the union of per-snapshot top-delegate tables (top 25 stored in timeseries json)

Notes / Definitions
-------------------
- "Bracket" here means bonded stake band at snapshot time (from event-replay).
- "Inflow/outflow" in this board is *not* a full decomposition of trades. It's
  evidence-backed proxies:
  - inflow: first-bond counts (new delegators) reaching a max-bonded band, by year
  - outflow: wallets that ever withdrew, and total withdrawn LPT, by max-bonded band
- Delegate gain/bleed uses the top-delegate tables present in the time-series
  dataset; it will miss smaller delegates that never appear in the top-25.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple


getcontext().prec = 60


BAND_LABELS = ["<1 LPT", "1–10 LPT", "10–100 LPT", "100–1k LPT", "1k–10k LPT", "10k+ LPT"]


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


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _format_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def _md_escape(text: str) -> str:
    return text.replace("<", "&lt;")


def _find_snapshot(snapshots: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    for s in snapshots:
        if s.get("label") == label:
            return s
    raise SystemExit(f"snapshot label not found: {label}")


def _latest_label(snapshots: List[Dict[str, Any]]) -> str:
    if not snapshots:
        raise SystemExit("no snapshots")
    return str(snapshots[-1].get("label"))


def _as_decimal(x: Any) -> Decimal:
    if x is None:
        return Decimal(0)
    if isinstance(x, Decimal):
        return x
    if isinstance(x, (int, float)):
        return Decimal(str(x))
    return Decimal(str(x))


def _band_row(s: Dict[str, Any], band: str) -> Dict[str, Any]:
    b = (s.get("bands") or {}).get(band) or {}
    return {
        "active_delegators": int(b.get("active_delegators") or 0),
        "bonded_lpt": _as_decimal(b.get("bonded_lpt") or "0"),
        "share_of_active_count": float(b.get("share_of_active_count") or 0.0),
        "share_of_bonded_lpt": float(b.get("share_of_bonded_lpt") or 0.0),
    }


def _snapshot_band_table(s: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {band: _band_row(s, band) for band in BAND_LABELS}


def _delegate_top_map(snapshot: Dict[str, Any]) -> Dict[str, Decimal]:
    out: Dict[str, Decimal] = {}
    top = ((snapshot.get("concentration") or {}).get("delegates") or {}).get("top_delegates") or []
    for row in top:
        delegate = str(row.get("delegate") or "").lower()
        if not delegate.startswith("0x") or len(delegate) != 42:
            continue
        out[delegate] = _as_decimal(row.get("bonded_lpt") or "0")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeseries-json", default="research/delegator-band-timeseries.json")
    parser.add_argument("--outflows-json", default="research/delegator-outflows-by-size-band.json")
    parser.add_argument("--from-label", default="2024-10-end", help="Snapshot label (e.g. 2024-10-end).")
    parser.add_argument("--to-label", default="", help="Snapshot label (default: latest).")
    parser.add_argument("--top-n-delegates", type=int, default=15)
    parser.add_argument("--out-md", default="research/delegation-board.md")
    parser.add_argument("--out-json", default="research/delegation-board.json")
    args = parser.parse_args()

    ts = _read_json(args.timeseries_json)
    snapshots = ts.get("snapshots") or []
    if not isinstance(snapshots, list) or not snapshots:
        raise SystemExit(f"bad timeseries json: {args.timeseries_json}")

    to_label = str(args.to_label or _latest_label(snapshots))
    s0 = _find_snapshot(snapshots, str(args.from_label))
    s1 = _find_snapshot(snapshots, to_label)

    t0 = _snapshot_band_table(s0)
    t1 = _snapshot_band_table(s1)

    # Net changes by bracket.
    net_rows: List[Dict[str, Any]] = []
    for band in BAND_LABELS:
        a0 = t0[band]["active_delegators"]
        a1 = t1[band]["active_delegators"]
        b0 = t0[band]["bonded_lpt"]
        b1 = t1[band]["bonded_lpt"]
        net_rows.append(
            {
                "band": band,
                "active_delegators_from": a0,
                "active_delegators_to": a1,
                "active_delegators_delta": int(a1 - a0),
                "bonded_lpt_from": str(b0),
                "bonded_lpt_to": str(b1),
                "bonded_lpt_delta": str(b1 - b0),
            }
        )

    # Delegate gain/bleed using top-25 maps.
    d0 = _delegate_top_map(s0)
    d1 = _delegate_top_map(s1)
    delegate_union = sorted(set(d0.keys()) | set(d1.keys()))
    delegate_deltas: List[Tuple[str, Decimal, Decimal, Decimal]] = []
    for d in delegate_union:
        v0 = d0.get(d, Decimal(0))
        v1 = d1.get(d, Decimal(0))
        delegate_deltas.append((d, v0, v1, v1 - v0))
    delegate_deltas.sort(key=lambda x: x[3], reverse=True)
    top_gainers = delegate_deltas[: max(0, int(args.top_n_delegates))]
    top_bleeders = sorted(delegate_deltas, key=lambda x: x[3])[: max(0, int(args.top_n_delegates))]

    # Inflow/outflow proxies from outflows report.
    of = _read_json(args.outflows_json)
    bands = of.get("bands") or {}
    new_by_year = of.get("new_delegators_by_year") or {}
    if not isinstance(bands, dict):
        bands = {}
    if not isinstance(new_by_year, dict):
        new_by_year = {}

    outflow_rows: List[Dict[str, Any]] = []
    for band in BAND_LABELS:
        b = bands.get(band) or {}
        outflow_rows.append(
            {
                "band": band,
                "delegators": int(b.get("delegators") or 0),
                "withdrawers": int(b.get("withdrawers") or 0),
                "withdraw_lpt": str(_as_decimal(b.get("withdraw_lpt") or "0")),
                "unbonders": int(b.get("unbonders") or 0),
                "unbond_lpt": str(_as_decimal(b.get("unbond_lpt") or "0")),
            }
        )

    inflow_year_rows: List[Dict[str, Any]] = []
    for year in sorted(new_by_year.keys()):
        yr = str(year)
        row = {"year": yr}
        total = 0
        for band in BAND_LABELS:
            v = int((new_by_year.get(yr) or {}).get(band) or 0)
            row[band] = v
            total += v
        row["total"] = total
        inflow_year_rows.append(row)

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "window": {
            "from_label": s0.get("label"),
            "from_snapshot_iso": s0.get("snapshot_iso"),
            "from_block": s0.get("snapshot_block"),
            "to_label": s1.get("label"),
            "to_snapshot_iso": s1.get("snapshot_iso"),
            "to_block": s1.get("snapshot_block"),
        },
        "bands_snapshot_from": {
            band: {
                "active_delegators": t0[band]["active_delegators"],
                "bonded_lpt": str(t0[band]["bonded_lpt"]),
                "share_of_active_count": t0[band]["share_of_active_count"],
                "share_of_bonded_lpt": t0[band]["share_of_bonded_lpt"],
            }
            for band in BAND_LABELS
        },
        "bands_snapshot_to": {
            band: {
                "active_delegators": t1[band]["active_delegators"],
                "bonded_lpt": str(t1[band]["bonded_lpt"]),
                "share_of_active_count": t1[band]["share_of_active_count"],
                "share_of_bonded_lpt": t1[band]["share_of_bonded_lpt"],
            }
            for band in BAND_LABELS
        },
        "bands_net": net_rows,
        "inflow_new_delegators_by_year": inflow_year_rows,
        "outflow_by_max_band": outflow_rows,
        "delegate_gain_bleed": {
            "note": "Computed using union of per-snapshot top-25 delegates; misses tail delegates that never appear in top-25.",
            "top_gainers": [
                {"delegate": d, "bonded_from": str(v0), "bonded_to": str(v1), "delta": str(dv)} for d, v0, v1, dv in top_gainers
            ],
            "top_bleeders": [
                {"delegate": d, "bonded_from": str(v0), "bonded_to": str(v1), "delta": str(dv)} for d, v0, v1, dv in top_bleeders
            ],
        },
    }

    _write_json_atomic(args.out_json, out_json)

    # Markdown board.
    lines: List[str] = []
    lines.append("# Livepeer (Arbitrum) — Delegation board")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(
        f"- Window: `{out_json['window']['from_label']}` ({out_json['window']['from_snapshot_iso']}) → `{out_json['window']['to_label']}` ({out_json['window']['to_snapshot_iso']})"
    )
    lines.append("")

    lines.append("## Delegator brackets (snapshot: to)")
    lines.append("")
    lines.append("| Band | Active wallets | Share (wallets) | Bonded LPT | Share (bonded) |")
    lines.append("|---|---:|---:|---:|---:|")
    for band in BAND_LABELS:
        r = t1[band]
        lines.append(
            f"| {_md_escape(band)} | {r['active_delegators']:,} | {_format_pct(r['share_of_active_count'])} | {_format_lpt(r['bonded_lpt'])} | {_format_pct(r['share_of_bonded_lpt'])} |"
        )
    lines.append("")

    lines.append("## Net change by bracket (from → to)")
    lines.append("")
    lines.append("| Band | Δ wallets | Δ bonded LPT | wallets (from→to) | bonded (from→to) |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in net_rows:
        band = row["band"]
        d_wallets = int(row["active_delegators_delta"])
        d_lpt = _as_decimal(row["bonded_lpt_delta"])
        lines.append(
            f"| {_md_escape(band)} | {d_wallets:+,} | {_format_lpt(d_lpt)} | {row['active_delegators_from']:,}→{row['active_delegators_to']:,} | {_format_lpt(_as_decimal(row['bonded_lpt_from']))}→{_format_lpt(_as_decimal(row['bonded_lpt_to']))} |"
        )
    lines.append("")

    lines.append("## Inflows (proxy): new delegators by year (first bond, grouped by max band reached)")
    lines.append("")
    lines.append("| Year | Total | &lt;1 | 1–10 | 10–100 | 100–1k | 1k–10k | 10k+ |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in inflow_year_rows:
        lines.append(
            f"| {row['year']} | {row['total']:,} | {row['<1 LPT']:,} | {row['1–10 LPT']:,} | {row['10–100 LPT']:,} | {row['100–1k LPT']:,} | {row['1k–10k LPT']:,} | {row['10k+ LPT']:,} |"
        )
    lines.append("")

    lines.append("## Outflows (proxy): withdrawers + withdrawn LPT (grouped by max band per wallet)")
    lines.append("")
    lines.append("| Band | Delegators | Withdrawers | Withdrawn LPT | Unbonders | Unbonded LPT |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in outflow_rows:
        lines.append(
            f"| {_md_escape(row['band'])} | {row['delegators']:,} | {row['withdrawers']:,} | {_format_lpt(_as_decimal(row['withdraw_lpt']))} | {row['unbonders']:,} | {_format_lpt(_as_decimal(row['unbond_lpt']))} |"
        )
    lines.append("")

    lines.append("## Orchestrator gain/bleed (delegate stake, from → to)")
    lines.append("")
    lines.append(out_json["delegate_gain_bleed"]["note"])
    lines.append("")
    lines.append("### Top gainers")
    lines.append("")
    lines.append("| Rank | Delegate | Δ bonded LPT | bonded (from→to) |")
    lines.append("|---:|---|---:|---:|")
    for i, (d, v0, v1, dv) in enumerate(top_gainers, start=1):
        lines.append(f"| {i} | `{d}` | {_format_lpt(dv)} | {_format_lpt(v0)}→{_format_lpt(v1)} |")
    lines.append("")
    lines.append("### Top bleeders")
    lines.append("")
    lines.append("| Rank | Delegate | Δ bonded LPT | bonded (from→to) |")
    lines.append("|---:|---|---:|---:|")
    for i, (d, v0, v1, dv) in enumerate(top_bleeders, start=1):
        lines.append(f"| {i} | `{d}` | {_format_lpt(dv)} | {_format_lpt(v0)}→{_format_lpt(v1)} |")
    lines.append("")

    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
