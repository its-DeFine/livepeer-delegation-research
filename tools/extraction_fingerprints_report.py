#!/usr/bin/env python3
"""
Livepeer — Extraction fingerprints (on-chain proxies).

Goal
----
We cannot directly observe off-chain hedges (CEX borrowing / perp shorts) on-chain.
But we *can* measure on-chain behaviors consistent with systematic extraction:

- rewards claimed vs reward-proxy withdrawn,
- whether top withdrawers remain bonded (harvest-without-exit),
- where post-withdraw LPT tends to route (bridge/burn-like vs EOAs vs contracts),
- claim cadence proxies (avg interval between claims).

This report is intentionally framed as "fingerprints" / proxies — not proof.

Inputs
------
- research/earnings-report.json
- research/outflow-destination-classification-top50.json
- artifacts/delegator-bonded-amounts-cache.json
- (optional) research/arbitrum-bridge-out-decode.json

Outputs
-------
- research/extraction-fingerprints.json
- research/extraction-fingerprints.md
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple


getcontext().prec = 60

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _d(x: Any) -> Decimal:
    return Decimal(str(x))


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _pct(x: Decimal) -> str:
    return f"{float(x) * 100:.2f}%"


def _parse_day(s: str) -> Optional[date]:
    if not isinstance(s, str) or not s:
        return None
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _days_between(a: Optional[date], b: Optional[date]) -> Optional[int]:
    if not a or not b:
        return None
    return abs((b - a).days)


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


@dataclass(frozen=True)
class WalletFingerprint:
    rank: int
    address: str
    rewards_claimed_lpt: Decimal
    proxy_rewards_withdrawn_lpt: Decimal
    withdraw_total_lpt: Decimal
    claim_events: int
    claim_span_days: Optional[int]
    avg_claim_interval_days: Optional[Decimal]
    still_bonded_lpt: Decimal
    post_withdraw_total_out_lpt: Optional[Decimal]
    post_withdraw_bridge_or_burn_lpt: Optional[Decimal]
    post_withdraw_direct_transfer_lpt: Optional[Decimal]
    post_withdraw_contract_interaction_lpt: Optional[Decimal]
    post_withdraw_bridge_or_burn_share: Optional[Decimal]
    post_withdraw_direct_transfer_share: Optional[Decimal]
    post_withdraw_contract_interaction_share: Optional[Decimal]
    bridge_out_decoded_lpt: Optional[Decimal]
    bridge_out_self_recipient_share: Optional[Decimal]
    archetype: str


def _classify_archetype(*, still_bonded_lpt: Decimal, reward_withdraw_ratio: Optional[Decimal]) -> str:
    """
    Best-effort heuristic labels to help stakeholders read the tables faster.
    These are not ground truth and should be treated as descriptive only.
    """

    # Large still-bonded wallets are important regardless of the ratio (ratio can be low if they have
    # huge lifetime rewards but only withdrew a portion).
    if still_bonded_lpt >= Decimal("1000000"):
        return "still bonded (very large)"
    if still_bonded_lpt >= Decimal("100000"):
        if reward_withdraw_ratio is not None and reward_withdraw_ratio >= Decimal("0.80"):
            return "harvester (still bonded)"
        return "still bonded (large)"
    if still_bonded_lpt >= Decimal("10000"):
        return "still bonded (mid)"

    if reward_withdraw_ratio is None:
        return "unknown"

    # Full exit: basically no bonded stake remains and withdrawals are mostly rewards.
    if still_bonded_lpt <= Decimal("1") and reward_withdraw_ratio >= Decimal("0.80"):
        return "exiter"

    if reward_withdraw_ratio < Decimal("0.25"):
        return "low-withdraw (likely compounding/holding)"

    return "mixed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--earnings-json", default="research/earnings-report.json")
    parser.add_argument("--outflow-json", default="research/outflow-destination-classification-top50.json")
    parser.add_argument("--bonded-cache-json", default="artifacts/delegator-bonded-amounts-cache.json")
    parser.add_argument("--bridge-decode-json", default="research/arbitrum-bridge-out-decode.json")
    parser.add_argument("--out-json", default="research/extraction-fingerprints.json")
    parser.add_argument("--out-md", default="research/extraction-fingerprints.md")
    args = parser.parse_args()

    earnings = _load_json(args.earnings_json)
    outflow = _load_json(args.outflow_json)
    bonded_cache = _load_json(args.bonded_cache_json)

    top = earnings.get("top_by_proxy_rewards_withdrawn") or []
    if not isinstance(top, list) or not top:
        raise SystemExit("earnings-report.json missing top_by_proxy_rewards_withdrawn list")

    outflow_wallets = outflow.get("wallets") or []
    outflow_by_addr: Dict[str, Dict[str, Any]] = {}
    if isinstance(outflow_wallets, list):
        for w in outflow_wallets:
            if not isinstance(w, dict):
                continue
            addr = w.get("address")
            if not isinstance(addr, str):
                continue
            try:
                outflow_by_addr[_normalize_address(addr)] = w
            except ValueError:
                continue

    bonded_wei_by_addr = bonded_cache.get("bonded_amount_wei_by_address") or {}
    if not isinstance(bonded_wei_by_addr, dict):
        bonded_wei_by_addr = {}

    bridge_meta_by_sender: Dict[str, Tuple[Decimal, Decimal]] = {}
    if args.bridge_decode_json and os.path.exists(args.bridge_decode_json):
        bridge = _load_json(args.bridge_decode_json)
        senders = bridge.get("senders") or []
        if isinstance(senders, list):
            for s in senders:
                if not isinstance(s, dict):
                    continue
                frm = s.get("from")
                if not isinstance(frm, str):
                    continue
                try:
                    frm = _normalize_address(frm)
                except ValueError:
                    continue
                burn_total_lpt = Decimal(str(s.get("burn_total_lpt") or "0"))
                self_share = Decimal(str(s.get("self_recipient_share") or "0"))
                bridge_meta_by_sender[frm] = (burn_total_lpt, self_share)

    fingerprints: List[WalletFingerprint] = []
    for idx, row in enumerate(top, start=1):
        if not isinstance(row, dict):
            continue
        addr = _normalize_address(row["address"])

        rewards_claimed = _d(row.get("rewards_lpt") or "0")
        proxy_withdrawn = _d(row.get("proxy_rewards_withdrawn_lpt") or "0")
        withdraw_total = _d(row.get("withdraw_lpt") or "0")
        claim_events = int(row.get("claim_events") or 0)

        first_day = _parse_day(str(row.get("first_claim_day") or ""))
        last_day = _parse_day(str(row.get("last_claim_day") or ""))
        span_days = _days_between(first_day, last_day)

        avg_interval: Optional[Decimal] = None
        if span_days is not None and claim_events > 1:
            avg_interval = Decimal(span_days) / Decimal(claim_events - 1)

        bonded_wei = bonded_wei_by_addr.get(addr)
        still_bonded = Decimal(0)
        try:
            if bonded_wei is not None:
                still_bonded = Decimal(int(bonded_wei)) / LPT_SCALE
        except Exception:
            still_bonded = Decimal(0)

        # Post-withdraw routing (only for wallets in the top50 outflow classification artifact).
        w = outflow_by_addr.get(addr)
        out_total: Optional[Decimal] = None
        burn_lpt: Optional[Decimal] = None
        eoa_lpt: Optional[Decimal] = None
        contract_lpt: Optional[Decimal] = None
        burn_share: Optional[Decimal] = None
        eoa_share: Optional[Decimal] = None
        contract_share: Optional[Decimal] = None

        if isinstance(w, dict):
            totals = w.get("totals") or {}
            cat = w.get("category_totals_lpt") or {}
            if isinstance(totals, dict) and isinstance(cat, dict):
                out_total = _d(totals.get("lpt_total_lpt") or "0")
                burn_lpt = _d(totals.get("lpt_to_zero_lpt") or "0")
                eoa_lpt = _d(totals.get("lpt_to_eoa_lpt") or "0")
                contract_lpt = _d(totals.get("lpt_to_contract_lpt") or "0")
                if out_total > 0:
                    burn_share = burn_lpt / out_total
                    eoa_share = eoa_lpt / out_total
                    contract_share = contract_lpt / out_total

        reward_withdraw_ratio: Optional[Decimal] = None
        if rewards_claimed > 0:
            reward_withdraw_ratio = min(Decimal(10), proxy_withdrawn / rewards_claimed)

        bridge_decoded_lpt: Optional[Decimal] = None
        bridge_self_share: Optional[Decimal] = None
        if addr in bridge_meta_by_sender:
            bridge_decoded_lpt, bridge_self_share = bridge_meta_by_sender[addr]

        fingerprints.append(
            WalletFingerprint(
                rank=idx,
                address=addr,
                rewards_claimed_lpt=rewards_claimed,
                proxy_rewards_withdrawn_lpt=proxy_withdrawn,
                withdraw_total_lpt=withdraw_total,
                claim_events=claim_events,
                claim_span_days=span_days,
                avg_claim_interval_days=avg_interval,
                still_bonded_lpt=still_bonded,
                post_withdraw_total_out_lpt=out_total,
                post_withdraw_bridge_or_burn_lpt=burn_lpt,
                post_withdraw_direct_transfer_lpt=eoa_lpt,
                post_withdraw_contract_interaction_lpt=contract_lpt,
                post_withdraw_bridge_or_burn_share=burn_share,
                post_withdraw_direct_transfer_share=eoa_share,
                post_withdraw_contract_interaction_share=contract_share,
                bridge_out_decoded_lpt=bridge_decoded_lpt,
                bridge_out_self_recipient_share=bridge_self_share,
                archetype=_classify_archetype(still_bonded_lpt=still_bonded, reward_withdraw_ratio=reward_withdraw_ratio),
            )
        )

    # Aggregate stats
    total_proxy = sum((w.proxy_rewards_withdrawn_lpt for w in fingerprints), Decimal(0))
    still_10k = sum((1 for w in fingerprints if w.still_bonded_lpt >= Decimal("10000")))
    still_100k = sum((1 for w in fingerprints if w.still_bonded_lpt >= Decimal("100000")))
    still_1m = sum((1 for w in fingerprints if w.still_bonded_lpt >= Decimal("1000000")))

    archetype_counts: Dict[str, int] = {}
    for w in fingerprints:
        archetype_counts[w.archetype] = archetype_counts.get(w.archetype, 0) + 1

    out_json = {
        "generated_from": {
            "earnings_json": str(args.earnings_json),
            "outflow_json": str(args.outflow_json),
            "bonded_cache_json": str(args.bonded_cache_json),
            "bridge_decode_json": str(args.bridge_decode_json) if os.path.exists(args.bridge_decode_json) else None,
        },
        "notes": [
            "This is a proxy/fingerprint report. It does not prove delta-neutral hedging, which is often off-chain.",
            "Claim cadence is estimated from first/last claim day and claim event count (not exact per-claim timing).",
            "Post-withdraw routing is based on the outflow classification artifact for the same top50 cohort.",
        ],
        "totals": {
            "wallets": len(fingerprints),
            "proxy_rewards_withdrawn_lpt_total_top50": str(total_proxy),
            "still_bonded_counts": {"ge_10k": still_10k, "ge_100k": still_100k, "ge_1m": still_1m},
            "archetypes": archetype_counts,
        },
        "wallets": [
            {
                "rank": w.rank,
                "address": w.address,
                "archetype": w.archetype,
                "rewards_claimed_lpt": str(w.rewards_claimed_lpt),
                "proxy_rewards_withdrawn_lpt": str(w.proxy_rewards_withdrawn_lpt),
                "withdraw_total_lpt": str(w.withdraw_total_lpt),
                "claim_events": w.claim_events,
                "claim_span_days": w.claim_span_days,
                "avg_claim_interval_days": (str(w.avg_claim_interval_days) if w.avg_claim_interval_days is not None else None),
                "still_bonded_lpt": str(w.still_bonded_lpt),
                "post_withdraw": {
                    "total_out_lpt": (str(w.post_withdraw_total_out_lpt) if w.post_withdraw_total_out_lpt is not None else None),
                    "bridge_or_burn_lpt": (str(w.post_withdraw_bridge_or_burn_lpt) if w.post_withdraw_bridge_or_burn_lpt is not None else None),
                    "direct_transfer_lpt": (str(w.post_withdraw_direct_transfer_lpt) if w.post_withdraw_direct_transfer_lpt is not None else None),
                    "contract_interaction_lpt": (str(w.post_withdraw_contract_interaction_lpt) if w.post_withdraw_contract_interaction_lpt is not None else None),
                    "bridge_or_burn_share": (str(w.post_withdraw_bridge_or_burn_share) if w.post_withdraw_bridge_or_burn_share is not None else None),
                    "direct_transfer_share": (str(w.post_withdraw_direct_transfer_share) if w.post_withdraw_direct_transfer_share is not None else None),
                    "contract_interaction_share": (str(w.post_withdraw_contract_interaction_share) if w.post_withdraw_contract_interaction_share is not None else None),
                },
                "bridge_out_decoded": {
                    "burn_total_lpt": (str(w.bridge_out_decoded_lpt) if w.bridge_out_decoded_lpt is not None else None),
                    "self_recipient_share": (str(w.bridge_out_self_recipient_share) if w.bridge_out_self_recipient_share is not None else None),
                },
            }
            for w in fingerprints
        ],
    }

    _write_json(args.out_json, out_json)

    # Markdown
    lines: List[str] = []
    lines.append("---")
    lines.append('title: "Extraction fingerprints (on-chain proxies)"')
    lines.append(
        'description: "A proxy dashboard for systematic reward extraction: rewards claimed vs withdrawn, post-withdraw routing, and whether top withdrawers remain bonded."'
    )
    lines.append('sidebar_label: "Extraction fingerprints"')
    lines.append("---")
    lines.append("")
    lines.append("# Extraction fingerprints (on-chain proxies)")
    lines.append("")
    lines.append(
        "We cannot directly see off-chain hedges (CEX borrowing / perp shorts) on-chain. "
        "But systematic extraction strategies often leave on-chain footprints: frequent claims, reward-withdraw behavior, "
        "post-withdraw routing (bridge-outs / EOAs), and cases where wallets keep large bonded stake while continuously withdrawing."
    )
    lines.append("")
    lines.append("This page summarizes **top-50 wallets by proxy rewards withdrawn** (from `research/earnings-report.json`).")
    lines.append("")

    lines.append("## Topline stats (top-50 cohort)")
    lines.append("")
    lines.append(f"- Proxy rewards withdrawn (sum): **{_format_lpt(total_proxy)} LPT**")
    lines.append(f"- Wallets still bonded ≥ `10k` LPT: **{still_10k} / {len(fingerprints)}**")
    lines.append(f"- Wallets still bonded ≥ `100k` LPT: **{still_100k} / {len(fingerprints)}**")
    if still_1m:
        lines.append(f"- Wallets still bonded ≥ `1m` LPT: **{still_1m} / {len(fingerprints)}**")
    lines.append("")
    lines.append("Archetypes (best-effort heuristics):")
    for k in sorted(archetype_counts.keys()):
        lines.append(f"- `{k}`: **{archetype_counts[k]}**")

    lines.append("")
    lines.append("## Wallet table (top-50 by proxy rewards withdrawn)")
    lines.append("")
    lines.append(
        "Columns: proxy rewards withdrawn, rewards claimed, reward-withdraw ratio, current bonded stake (snapshot), "
        "claim cadence proxy, and post-withdraw routing shares."
    )
    lines.append("")
    lines.append(
        "| Rank | Address | Archetype | Proxy rewards withdrawn | Rewards claimed | Ratio | Bonded now | Avg claim interval | Bridge/burn share | EOA share |"
    )
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for w in fingerprints:
        ratio = (w.proxy_rewards_withdrawn_lpt / w.rewards_claimed_lpt) if w.rewards_claimed_lpt > 0 else Decimal(0)
        avg_claim = _format_lpt(w.avg_claim_interval_days, places=1) if w.avg_claim_interval_days is not None else "n/a"
        burn_share = _pct(w.post_withdraw_bridge_or_burn_share) if w.post_withdraw_bridge_or_burn_share is not None else "n/a"
        eoa_share = _pct(w.post_withdraw_direct_transfer_share) if w.post_withdraw_direct_transfer_share is not None else "n/a"
        lines.append(
            f"| {w.rank} | `{w.address}` | `{w.archetype}` | {_format_lpt(w.proxy_rewards_withdrawn_lpt)} | {_format_lpt(w.rewards_claimed_lpt)} | {_pct(ratio)} | {_format_lpt(w.still_bonded_lpt)} | {avg_claim} d | {burn_share} | {eoa_share} |"
        )

    # Focus tables
    lines.append("")
    lines.append("## Top still-bonded withdrawers (subset)")
    lines.append("")
    lines.append("These are the most relevant wallets for a “harvest without exit” fingerprint (still bonded while withdrawing).")
    lines.append("")
    still_sorted = sorted(fingerprints, key=lambda w: w.still_bonded_lpt, reverse=True)[:12]
    lines.append("| Rank | Address | Bonded now | Proxy rewards withdrawn | Bridge/burn share |")
    lines.append("|---:|---|---:|---:|---:|")
    for w in still_sorted:
        burn_share = _pct(w.post_withdraw_bridge_or_burn_share) if w.post_withdraw_bridge_or_burn_share is not None else "n/a"
        lines.append(
            f"| {w.rank} | `{w.address}` | {_format_lpt(w.still_bonded_lpt)} | {_format_lpt(w.proxy_rewards_withdrawn_lpt)} | {burn_share} |"
        )

    lines.append("")
    lines.append("## Notes + limitations")
    lines.append("")
    lines.append("- This report is **not proof** of delta-neutral hedging; it is a set of on-chain proxies.")
    lines.append("- Claim cadence is approximate (we only use first/last claim day + number of claim events).")
    lines.append("- Post-withdraw routing uses a small label set; unlabeled EOAs can still be CEX deposit wallets.")
    lines.append("- For bridge-outs specifically, see `/research/l1-bridge-recipient-followup` and `/research/l1-bridge-recipient-second-hop`.")

    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
