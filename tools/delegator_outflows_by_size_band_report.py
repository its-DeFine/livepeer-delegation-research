#!/usr/bin/env python3
"""
Livepeer delegator outflows by delegator "size band" (Arbitrum).

Goal:
- Answer: which delegator size cohorts do outflows come from (by count vs by LPT)?
- Provide an evidence-backed "are bands growing?" view using new-delegator inflows per year.

Data sources:
- `delegators_state.pkl` produced by the workspace scan tool
  (`tools/livepeer/arb_bondingmanager_scan.py` in the main workspace repo).
  This contains event-derived per-delegator aggregates:
    - first_bond_ts, max_bonded_amount, withdraw_events, total_withdraw_amount, etc.
- `data/arbitrum_delegator_addresses.json` committed in this repo (universe selection).

Notes:
- Size bands are based on each wallet's historical `max_bonded_amount` (max observed bonded stake),
  not its bonded stake at the exact withdrawal moment.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional


getcontext().prec = 50

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS


@dataclass(frozen=True)
class Band:
    label: str
    low_inclusive_lpt: Decimal
    high_inclusive_lpt: Optional[Decimal]  # None => infinity


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _format_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def _md_escape(text: str) -> str:
    # Docusaurus parses Markdown as MDX; raw `<1` can be interpreted as JSX and break builds.
    return text.replace("<", "&lt;")


def _read_addresses(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    addresses = payload["addresses"] if isinstance(payload, dict) else payload
    if not isinstance(addresses, list) or not addresses:
        raise SystemExit(f"addresses json missing 'addresses' list: {path}")
    return [str(a).lower() for a in addresses]


def _read_delegators_state(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        return pickle.load(f)


def _band_for_max_bonded(max_bonded_lpt: Decimal) -> Optional[str]:
    if max_bonded_lpt <= 0:
        return None
    if max_bonded_lpt < 1:
        return "<1 LPT"
    if max_bonded_lpt <= 10:
        return "1–10 LPT"
    if max_bonded_lpt <= 100:
        return "10–100 LPT"
    if max_bonded_lpt <= 1000:
        return "100–1k LPT"
    if max_bonded_lpt <= 10000:
        return "1k–10k LPT"
    return "10k+ LPT"


def _write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--delegators-state-pkl",
        default=os.path.join("..", "..", "artifacts", "livepeer-bm-scan-arbitrum-v2", "delegators_state.pkl"),
        help="Path to delegators_state.pkl (produced by the workspace scan).",
    )
    parser.add_argument("--addresses-json", default="data/arbitrum_delegator_addresses.json")
    parser.add_argument("--out-md", default="research/delegator-outflows-by-size-band.md")
    parser.add_argument("--out-json", default="research/delegator-outflows-by-size-band.json")
    args = parser.parse_args()

    addresses = _read_addresses(args.addresses_json)
    address_set = set(addresses)

    state = _read_delegators_state(args.delegators_state_pkl)
    delegators = state.get("delegators")
    if not isinstance(delegators, dict):
        raise SystemExit("delegators_state.pkl missing 'delegators' dict")

    bands: List[Band] = [
        Band("<1 LPT", Decimal("0"), Decimal("1")),
        Band("1–10 LPT", Decimal("1"), Decimal("10")),
        Band("10–100 LPT", Decimal("10"), Decimal("100")),
        Band("100–1k LPT", Decimal("100"), Decimal("1000")),
        Band("1k–10k LPT", Decimal("1000"), Decimal("10000")),
        Band("10k+ LPT", Decimal("10000"), None),
    ]
    labels = [b.label for b in bands]

    by_band = {
        label: {
            "delegators": 0,
            "withdrawers": 0,
            "unbonders": 0,
            "withdraw_lpt": Decimal(0),
            "unbond_lpt": Decimal(0),
        }
        for label in labels
    }

    total_delegators = 0
    total_withdrawers = 0
    total_unbonders = 0
    total_withdraw_lpt = Decimal(0)
    total_unbond_lpt = Decimal(0)

    new_by_year: Dict[int, Dict[str, int]] = {}
    threshold_defs = [
        ("≥10k LPT", Decimal("10000")),
        ("≥100k LPT", Decimal("100000")),
    ]
    by_threshold = {
        label: {
            "threshold_lpt": thr,
            "delegators": 0,
            "withdrawers": 0,
            "unbonders": 0,
            "withdraw_lpt": Decimal(0),
            "unbond_lpt": Decimal(0),
        }
        for label, thr in threshold_defs
    }
    new_by_year_thresholds: Dict[int, Dict[str, int]] = {}

    # 1) Outflows by band
    for addr, e in delegators.items():
        a = str(addr).lower()
        if a not in address_set:
            continue
        if e.get("first_bond_ts") is None:
            continue

        max_bonded_lpt = _wei_to_lpt(int(e.get("max_bonded_amount") or 0))
        label = _band_for_max_bonded(max_bonded_lpt)
        if not label:
            continue

        fb_year = datetime.fromtimestamp(int(e["first_bond_ts"]), tz=timezone.utc).year

        total_delegators += 1
        by_band[label]["delegators"] += 1

        if fb_year not in new_by_year:
            new_by_year[fb_year] = {l: 0 for l in labels}
        new_by_year[fb_year][label] += 1

        if fb_year not in new_by_year_thresholds:
            new_by_year_thresholds[fb_year] = {k: 0 for k in by_threshold.keys()}

        for t_label, thr in threshold_defs:
            if max_bonded_lpt < thr:
                continue
            by_threshold[t_label]["delegators"] += 1
            new_by_year_thresholds[fb_year][t_label] += 1

        if int(e.get("withdraw_events") or 0) > 0:
            total_withdrawers += 1
            by_band[label]["withdrawers"] += 1
            w_lpt = _wei_to_lpt(int(e.get("total_withdraw_amount") or 0))
            by_band[label]["withdraw_lpt"] += w_lpt
            total_withdraw_lpt += w_lpt
            for t_label, thr in threshold_defs:
                if max_bonded_lpt < thr:
                    continue
                by_threshold[t_label]["withdrawers"] += 1
                by_threshold[t_label]["withdraw_lpt"] += w_lpt

        if int(e.get("unbond_events") or 0) > 0:
            total_unbonders += 1
            by_band[label]["unbonders"] += 1
            u_lpt = _wei_to_lpt(int(e.get("total_unbond_amount") or 0))
            by_band[label]["unbond_lpt"] += u_lpt
            total_unbond_lpt += u_lpt
            for t_label, thr in threshold_defs:
                if max_bonded_lpt < thr:
                    continue
                by_threshold[t_label]["unbonders"] += 1
                by_threshold[t_label]["unbond_lpt"] += u_lpt

    # 2) Compose report payload
    out: Dict[str, Any] = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "delegators_state_pkl": args.delegators_state_pkl,
            "addresses_json": args.addresses_json,
            "source_meta": {
                "rpc_url": state.get("rpc_url"),
                "bonding_manager": state.get("address"),
                "from_block": state.get("from_block"),
                "to_block": state.get("to_block"),
                "updated_at_utc": state.get("updated_at_utc"),
            },
        },
        "definition": {
            "band_basis": "max_bonded_amount (historical max observed bonded stake per wallet)",
            "outflow_signal": {
                "withdraw": "WithdrawStake events (cashout) aggregated per wallet: total_withdraw_amount",
                "unbond": "Unbond events aggregated per wallet: total_unbond_amount",
            },
        },
        "totals": {
            "delegators_in_universe": total_delegators,
            "withdrawers": total_withdrawers,
            "unbonders": total_unbonders,
            "withdraw_total_lpt": str(total_withdraw_lpt),
            "unbond_total_lpt": str(total_unbond_lpt),
        },
        "bands": {},
        "thresholds": {},
        "new_delegators_by_year": new_by_year,
        "new_delegators_by_year_thresholds": new_by_year_thresholds,
    }

    for label in labels:
        s = by_band[label]
        out["bands"][label] = {
            "delegators": s["delegators"],
            "withdrawers": s["withdrawers"],
            "unbonders": s["unbonders"],
            "withdraw_lpt": str(s["withdraw_lpt"]),
            "unbond_lpt": str(s["unbond_lpt"]),
            "share_of_delegators": (s["delegators"] / total_delegators) if total_delegators else 0,
            "share_of_withdrawers": (s["withdrawers"] / total_withdrawers) if total_withdrawers else 0,
            "share_of_unbonders": (s["unbonders"] / total_unbonders) if total_unbonders else 0,
            "share_of_withdraw_lpt": (float(s["withdraw_lpt"] / total_withdraw_lpt) if total_withdraw_lpt else 0),
            "share_of_unbond_lpt": (float(s["unbond_lpt"] / total_unbond_lpt) if total_unbond_lpt else 0),
        }

    for t_label, s in by_threshold.items():
        out["thresholds"][t_label] = {
            "threshold_lpt": str(s["threshold_lpt"]),
            "delegators": s["delegators"],
            "withdrawers": s["withdrawers"],
            "unbonders": s["unbonders"],
            "withdraw_lpt": str(s["withdraw_lpt"]),
            "unbond_lpt": str(s["unbond_lpt"]),
            "share_of_delegators": (s["delegators"] / total_delegators) if total_delegators else 0,
            "share_of_withdrawers": (s["withdrawers"] / total_withdrawers) if total_withdrawers else 0,
            "share_of_withdraw_lpt": (float(s["withdraw_lpt"] / total_withdraw_lpt) if total_withdraw_lpt else 0),
        }

    _write_json_atomic(args.out_json, out)

    # 3) Markdown report
    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("# Livepeer Delegator Outflows — By Delegator Size Band (Arbitrum)\n\n")
        f.write("This report answers:\n")
        f.write("- Which delegator size cohorts drive outflows (by **count** vs by **LPT**)?\n")
        f.write("- Are size bands growing (via **new delegators per year**) or shrinking?\n\n")

        f.write("## Inputs\n\n")
        f.write(f"- Universe: `data/arbitrum_delegator_addresses.json` ({len(addresses):,} addresses)\n")
        f.write(f"- State aggregates: `{args.delegators_state_pkl}`\n")
        f.write(f"- Scan window: blocks `{state.get('from_block')}` → `{state.get('to_block')}` (updated `{state.get('updated_at_utc')}`)\n\n")

        f.write("## Outflows by size band (band = max bonded stake per wallet)\n\n")
        f.write(f"- Total delegators in universe (first bond observed): `{total_delegators:,}`\n")
        f.write(f"- Wallets that ever withdrew stake (`WithdrawStake`): `{total_withdrawers:,}` (total withdrawn: `{_format_lpt(total_withdraw_lpt)} LPT`)\n")
        f.write(f"- Wallets that ever unbonded (`Unbond`): `{total_unbonders:,}` (total unbonded: `{_format_lpt(total_unbond_lpt)} LPT`)\n\n")

        f.write("| Band (max bonded) | Delegators | Withdrawers | % of withdrawers | Withdrawn LPT | % of withdrawn |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for label in labels:
            row = out["bands"][label]
            f.write(
                f"| {_md_escape(label)} | {row['delegators']:,} | {row['withdrawers']:,} | {_format_pct(row['share_of_withdrawers'])} | {_format_lpt(Decimal(row['withdraw_lpt']))} | {_format_pct(row['share_of_withdraw_lpt'])} |\n"
            )

        f.write("\n### Interpretation (quick)\n\n")
        f.write("- **Withdrawn LPT** is expected to be concentrated in `10k+` (whale-size wallets).\n")
        f.write("- **Withdrawer count** tends to be concentrated in the mid-size retail bands (`10–100`, `100–1k`).\n\n")

        f.write("## High-stake cohorts (by max bonded threshold)\n\n")
        f.write("| Cohort | Delegators | Withdrawers | % of withdrawers | Withdrawn LPT | % of withdrawn |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for t_label, _thr in threshold_defs:
            row = out["thresholds"][t_label]
            f.write(
                f"| {t_label} | {row['delegators']:,} | {row['withdrawers']:,} | {_format_pct(row['share_of_withdrawers'])} | {_format_lpt(Decimal(row['withdraw_lpt']))} | {_format_pct(row['share_of_withdraw_lpt'])} |\n"
            )

        f.write("\n### New delegators reaching high-stake thresholds\n\n")
        years2 = sorted(new_by_year_thresholds.keys())
        if years2:
            f.write("| Year | ≥10k | ≥100k |\n")
            f.write("|---:|---:|---:|\n")
            for y in years2:
                row = new_by_year_thresholds[y]
                f.write(f"| {y} | {row.get('≥10k LPT', 0):,} | {row.get('≥100k LPT', 0):,} |\n")
        else:
            f.write("No `first_bond_ts` data found.\n")
        f.write("\n")

        f.write("## New delegators by year (first bond timestamp)\n\n")
        years = sorted(new_by_year.keys())
        if years:
            f.write("| Year | Total | &lt;1 | 1–10 | 10–100 | 100–1k | 1k–10k | 10k+ |\n")
            f.write("|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for y in years:
                row = new_by_year[y]
                total = sum(row.values())
                f.write(
                    f"| {y} | {total:,} | {row['<1 LPT']:,} | {row['1–10 LPT']:,} | {row['10–100 LPT']:,} | {row['100–1k LPT']:,} | {row['1k–10k LPT']:,} | {row['10k+ LPT']:,} |\n"
                )
        else:
            f.write("No `first_bond_ts` data found.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
