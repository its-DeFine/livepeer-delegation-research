#!/usr/bin/env python3
"""
Cross-protocol exchange-routing metrics (best-effort, on-chain).

Goal
----
We have multiple evidence packs that answer variants of:
  "After an unstake/withdrawal or a bridge-out, how much of the token flow ends up
   at labeled exchange hot wallets within a window and limited number of hops?"

This tool standardizes those outputs into a small, comparable summary so the
"X% goes to exchanges" claim is:
- clearly defined (what is the denominator? what is the selection? what window? how many hops?),
- reproducible (points at the underlying evidence pack JSON),
- explicitly treated as a LOWER BOUND (label sets are incomplete).

Currently supported sources:
- Livepeer (Ethereum L1): `research/l1-bridge-recipient-second-hop.json`
- Livepeer (Arbitrum→Ethereum): `research/extraction-timing-traces.json`
- The Graph (Ethereum): `research/thegraph-delegation-withdrawal-routing.json`
- Generic ERC20 exit routing packs (Ethereum):
  - Curve (veCRV): `research/curve-vecrv-exit-routing.json`
  - Frax (veFXS): `research/frax-vefxs-exit-routing.json`
  - Aave (stkAAVE Redeem): `research/aave-stkaave-redeem-exit-routing.json`
Context sources (non exchange-routing; used for interpretation):
- Filecoin lock/burn primitives: `research/filecoin-lock-burn-metrics.json`
- DePIN exit-friction snapshot: `research/depin-liquidity-primitives-snapshot.json`
- Theta unstake delay evidence: `research/theta-liquidity-primitives.json`

Outputs
-------
- research/exchange-routing-metrics.json
- research/exchange-routing-metrics.md
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict


getcontext().prec = 80


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _d(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(0)


def _pct(n: Decimal, d: Decimal) -> Decimal:
    if d <= 0:
        return Decimal(0)
    return (n / d) * Decimal(100)


def _fmt_pct(x: Decimal, *, places: int = 2) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):.2f}%"


def _count_exchange_labels(labels: dict[str, Any]) -> int:
    if not isinstance(labels, dict):
        return 0
    n = 0
    for _addr, meta in labels.items():
        if isinstance(meta, dict) and str(meta.get("category") or "") == "exchange":
            n += 1
    return n


def _livepeer_second_hop_metrics(path: str, *, exchange_label_count: int | None = None) -> dict[str, Any]:
    data = _read_json(path)
    totals = data.get("totals") if isinstance(data, dict) else {}
    category_totals = data.get("category_totals") if isinstance(data, dict) else {}
    selection = data.get("selection") if isinstance(data, dict) else {}
    rng = data.get("range") if isinstance(data, dict) else {}

    total_out = _d((totals or {}).get("outgoing_lpt"))
    total_in = _d((totals or {}).get("inbound_lpt"))
    to_ex = _d((category_totals or {}).get("exchange"))
    to_unknown = _d((category_totals or {}).get("unknown_eoa"))

    addr_count = len(data.get("addresses") or []) if isinstance(data, dict) and isinstance(data.get("addresses"), list) else 0
    min_in = (selection or {}).get("min_inbound_lpt")

    return {
        "source_json": path,
        "chain": "ethereum",
        "token": "LPT",
        "flow": "bridge-out follow-up: first-hop unknown EOAs → second-hop destinations",
        "denominator": {
            "basis": "total outgoing LPT from selected L1 EOAs (within block range)",
            "amount_lpt": str(total_out),
        },
        "numerator": {
            "basis": "outgoing LPT from selected L1 EOAs to labeled exchange endpoints",
            "amount_lpt": str(to_ex),
        },
        "share_to_exchanges_lower_bound_percent": str(_pct(to_ex, total_out)),
        "share_to_unknown_eoas_percent": str(_pct(to_unknown, total_out)),
        "exchange_outflow_vs_inbound_percent": str(_pct(to_ex, total_in)) if total_in > 0 else None,
        "selection": {
            "addresses_selected": addr_count,
            "min_inbound_lpt_from_bridge_recipients": float(min_in) if min_in is not None else None,
            "total_inbound_lpt_from_bridge_recipients": str(total_in),
            "block_range": {"from_block": (rng or {}).get("from_block"), "to_block": (rng or {}).get("to_block")},
        },
        "labels": {"exchange_label_count": int(exchange_label_count) if isinstance(exchange_label_count, int) else None},
        "notes": [
            "This is a LOWER BOUND: it counts only transfers to a small curated set of labeled exchange hot wallets.",
            "The share is conditional on the selection rule (large L1 unknown-EOA destinations of bridge recipients).",
            "The inbound-normalized ratio uses total inbound volume but does not attribute sources for each outflow (EOAs may have pre-existing balances).",
        ],
    }


def _thegraph_withdrawal_routing_metrics(path: str) -> dict[str, Any]:
    data = _read_json(path)
    analysis = data.get("analysis") if isinstance(data, dict) else {}
    res = data.get("routing_results_top_delegators") if isinstance(data, dict) else {}

    withdraw_events = int((res or {}).get("withdraw_events_considered") or 0)
    withdrawn = _d((res or {}).get("withdrawn_grt_considered"))

    matched_total_events = int((res or {}).get("matched_total_to_exchange_within_window_events") or 0)
    matched_total = _d((res or {}).get("matched_total_to_exchange_within_window_grt"))

    matched_2hop_events = int((res or {}).get("matched_second_hop_to_exchange_within_window_events") or 0)
    matched_2hop = _d((res or {}).get("matched_second_hop_to_exchange_within_window_grt"))

    matched_3hop_events = int((res or {}).get("matched_third_hop_to_exchange_within_window_events") or 0)
    matched_3hop = _d((res or {}).get("matched_third_hop_to_exchange_within_window_grt"))

    window_days = int((analysis or {}).get("window_days") or 0)
    top_n = int((analysis or {}).get("top_n_delegators") or 0)
    exchange_labels = int((analysis or {}).get("labels_exchange_count") or 0)

    first_hop_destinations: dict[str, Any] | None = None
    fh = (res or {}).get("first_hop_breakdown") if isinstance(res, dict) else None
    if isinstance(fh, dict):
        cat_counts = fh.get("category_counts") or {}
        cat_withdrawn = fh.get("category_withdrawn_grt") or {}
        cat_first_hop = fh.get("category_first_hop_grt") or {}

        shares: dict[str, str] = {}
        if isinstance(cat_withdrawn, dict):
            for k, v in cat_withdrawn.items():
                shares[str(k)] = str(_pct(_d(v), withdrawn))

        first_hop_destinations = {
            "method": fh.get("method"),
            "category_counts": cat_counts if isinstance(cat_counts, dict) else {},
            "category_withdrawn_grt": cat_withdrawn if isinstance(cat_withdrawn, dict) else {},
            "category_first_hop_grt": cat_first_hop if isinstance(cat_first_hop, dict) else {},
            "category_withdrawn_share_percent": shares,
            "notes": [
                "Categories are based on the FIRST outgoing transfer after withdrawal that meets the evidence pack’s threshold (amount and window constraints).",
                "Unknown categories are resolved via (a) label set membership and (b) eth_getCode for EOA vs contract when enabled.",
            ],
        }

    return {
        "source_json": path,
        "chain": "ethereum",
        "token": "GRT",
        "flow": "delegation withdrawal → exchange routing (0–3 hops within window)",
        "denominator": {"basis": "withdrawn GRT (top delegators considered)", "amount_grt": str(withdrawn), "events": withdraw_events},
        "numerator": {
            "basis": "withdrawn GRT that reaches labeled exchange endpoints within window (any hop)",
            "amount_grt": str(matched_total),
            "events": matched_total_events,
        },
        "share_to_exchanges_lower_bound_percent": str(_pct(matched_total, withdrawn)),
        "share_events_matched_percent": str(_pct(Decimal(matched_total_events), Decimal(withdraw_events))),
        "breakdown": {
            "second_hop": {
                "events": matched_2hop_events,
                "amount_grt": str(matched_2hop),
                "share_percent": str(_pct(matched_2hop, withdrawn)),
            },
            "third_hop": {
                "events": matched_3hop_events,
                "amount_grt": str(matched_3hop),
                "share_percent": str(_pct(matched_3hop, withdrawn)),
            },
        },
        "selection": {"window_days": window_days, "top_n_delegators": top_n},
        "labels": {"exchange_label_count": exchange_labels},
        "first_hop_destinations": first_hop_destinations,
        "notes": [
            "This is a LOWER BOUND: it counts only transfers to a small curated set of labeled exchange hot wallets.",
            "Routing is checked within a fixed post-withdrawal window and limited hops; more complex paths will be missed.",
        ],
    }


def _erc20_exit_routing_metrics(path: str) -> dict[str, Any]:
    data = _read_json(path)
    analysis = data.get("analysis") if isinstance(data, dict) else {}
    proto = data.get("protocol") if isinstance(data, dict) else {}
    tok = data.get("token") if isinstance(data, dict) else {}
    res = data.get("routing_results_top_recipients") if isinstance(data, dict) else {}
    arb = (res or {}).get("arbitrum_followup") if isinstance(res, dict) else None
    roles = (res or {}).get("post_exit_roles") if isinstance(res, dict) else None

    protocol_name = str((proto or {}).get("name") or "unknown")
    chain = str((proto or {}).get("chain") or "ethereum")
    token_symbol = str((tok or {}).get("symbol") or "token")

    exit_events = int((res or {}).get("exit_events_considered") or 0)
    exited = _d((res or {}).get("exit_amount_considered"))

    matched_total_events = int((res or {}).get("matched_total_to_exchange_within_window_events") or 0)
    matched_total = _d((res or {}).get("matched_total_to_exchange_within_window_amount"))

    matched_direct_events = int((res or {}).get("matched_direct_to_exchange_within_window_events") or 0)
    matched_direct = _d((res or {}).get("matched_direct_to_exchange_within_window_amount"))

    matched_2hop_events = int((res or {}).get("matched_second_hop_to_exchange_within_window_events") or 0)
    matched_2hop = _d((res or {}).get("matched_second_hop_to_exchange_within_window_amount"))

    matched_3hop_events = int((res or {}).get("matched_third_hop_to_exchange_within_window_events") or 0)
    matched_3hop = _d((res or {}).get("matched_third_hop_to_exchange_within_window_amount"))

    window_days = int((analysis or {}).get("window_days") or 0)
    top_n = int((analysis or {}).get("top_n") or 0)
    exchange_labels = int((analysis or {}).get("labels_exchange_count") or 0)

    first_hop_destinations: dict[str, Any] | None = None
    fh = (res or {}).get("first_hop_breakdown") if isinstance(res, dict) else None
    if isinstance(fh, dict):
        cat_counts = fh.get("category_counts") or {}
        cat_exited = fh.get("category_exit_amount") or {}
        cat_first_hop = fh.get("category_first_hop_amount") or {}

        shares: dict[str, str] = {}
        if isinstance(cat_exited, dict):
            for k, v in cat_exited.items():
                shares[str(k)] = str(_pct(_d(v), exited))

        first_hop_destinations = {
            "method": fh.get("method"),
            "category_counts": cat_counts if isinstance(cat_counts, dict) else {},
            "category_exit_amount": cat_exited if isinstance(cat_exited, dict) else {},
            "category_first_hop_amount": cat_first_hop if isinstance(cat_first_hop, dict) else {},
            "category_exit_share_percent": shares,
        }

    arbitrum_followup: dict[str, Any] | None = None
    if isinstance(arb, dict) and bool(arb.get("enabled")):
        deposit_events = int(arb.get("bridge_deposit_events") or 0)
        deposit_exit_amount = _d(arb.get("bridge_deposit_exit_amount"))
        deposit_token_amount = _d(arb.get("bridge_deposit_token_amount"))

        matched_events = int(arb.get("matched_to_exchange_events") or 0)
        matched_exit_amount = _d(arb.get("matched_to_exchange_exit_amount"))
        matched_token_amount = _d(arb.get("matched_to_exchange_token_amount"))

        arbitrum_followup = {
            "enabled": True,
            "deposit_events": deposit_events,
            "deposit_exit_amount": str(deposit_exit_amount),
            "deposit_token_amount": str(deposit_token_amount),
            "matched_to_exchange_events": matched_events,
            "matched_to_exchange_exit_amount": str(matched_exit_amount),
            "matched_to_exchange_token_amount": str(matched_token_amount),
            "matched_exit_share_of_total_exited_percent": str(_pct(matched_exit_amount, exited)),
            "matched_exit_share_of_deposit_exit_amount_percent": str(_pct(matched_exit_amount, deposit_exit_amount)),
            "matched_event_share_of_total_events_percent": str(_pct(Decimal(matched_events), Decimal(exit_events))),
            "top_exchange_endpoints_by_count": arb.get("top_exchange_endpoints_by_count") if isinstance(arb.get("top_exchange_endpoints_by_count"), list) else [],
        }

    post_exit_roles: dict[str, Any] | None = None
    if isinstance(roles, dict):
        role_counts = roles.get("role_counts") if isinstance(roles.get("role_counts"), dict) else {}
        role_exit_share = roles.get("role_exit_share_percent") if isinstance(roles.get("role_exit_share_percent"), dict) else {}
        post_exit_roles = {
            "role_counts": role_counts,
            "role_exit_share_percent": role_exit_share,
        }

    # "Expanded heuristic" = strict exchange share + (non-exchange) bridge deposit share (when available).
    exchange_share = _pct(matched_total, exited)
    bridge_share = Decimal(0)
    if isinstance(post_exit_roles, dict):
        try:
            bridge_share = _d((post_exit_roles.get("role_exit_share_percent") or {}).get("bridge_deposit"))
        except Exception:
            bridge_share = Decimal(0)

    return {
        "source_json": path,
        "chain": chain,
        "token": token_symbol,
        "protocol": protocol_name,
        "flow": "exit event → exchange routing (0–3 hops within window)",
        "denominator": {"basis": f"exited {token_symbol} (top recipients considered)", "amount": str(exited), "events": exit_events},
        "numerator": {
            "basis": f"exited {token_symbol} that reaches labeled exchange endpoints within window (any hop)",
            "amount": str(matched_total),
            "events": matched_total_events,
        },
        "share_to_exchanges_lower_bound_percent": str(_pct(matched_total, exited)),
        "share_to_exchanges_or_bridges_heuristic_percent": str(exchange_share + bridge_share),
        "share_events_matched_percent": str(_pct(Decimal(matched_total_events), Decimal(exit_events))),
        "breakdown": {
            "direct": {"events": matched_direct_events, "amount": str(matched_direct), "share_percent": str(_pct(matched_direct, exited))},
            "second_hop": {"events": matched_2hop_events, "amount": str(matched_2hop), "share_percent": str(_pct(matched_2hop, exited))},
            "third_hop": {"events": matched_3hop_events, "amount": str(matched_3hop), "share_percent": str(_pct(matched_3hop, exited))},
        },
        "selection": {"window_days": window_days, "top_n_recipients": top_n},
        "labels": {"exchange_label_count": exchange_labels},
        "first_hop_destinations": first_hop_destinations,
        "arbitrum_followup": arbitrum_followup,
        "post_exit_roles": post_exit_roles,
        "notes": [
            "This is a LOWER BOUND: it counts only transfers to a small curated set of labeled exchange hot wallets.",
            "Routing is checked within a fixed post-exit window and limited hops; more complex paths will be missed.",
        ],
    }


def _livepeer_extraction_timing_traces_metrics(
    path: str, *, exchange_label_count: int | None = None
) -> dict[str, Any]:
    data = _read_json(path)
    totals = data.get("totals") if isinstance(data, dict) else {}
    params = data.get("params") if isinstance(data, dict) else {}
    cycles = data.get("cycles") if isinstance(data, dict) else []

    withdraw_total = Decimal(0)
    receipt_total = Decimal(0)
    exchange_total = Decimal(0)
    withdraw_events = 0
    receipt_events = 0
    exchange_events = 0

    if isinstance(cycles, list):
        for c in cycles:
            if not isinstance(c, dict):
                continue

            w = c.get("l2_withdraw") or {}
            if isinstance(w, dict) and w.get("amount_lpt") is not None:
                withdraw_total += _d(w.get("amount_lpt"))
                withdraw_events += 1

            r = c.get("l1_receipt") or {}
            if isinstance(r, dict) and r.get("amount_lpt") is not None:
                receipt_total += _d(r.get("amount_lpt"))
                receipt_events += 1

            dep = c.get("l1_exchange_deposit") or None
            if isinstance(dep, dict) and dep.get("amount_lpt") is not None:
                exchange_total += _d(dep.get("amount_lpt"))
                exchange_events += 1

    senders_analyzed = int((totals or {}).get("senders") or 0)
    matched_receipt_to_exchange_events = int((totals or {}).get("matched_receipt_to_exchange") or 0)
    matched_burn_to_receipt_events = int((totals or {}).get("matched_burn_to_receipt") or 0)

    return {
        "source_json": path,
        "chain": "arbitrum+ethereum",
        "token": "LPT",
        "flow": "WithdrawStake → bridge-out → L1 escrow receipt → exchange routing (tight windows; ≤1 intermediate hop)",
        "denominator": {
            "basis": "L1 escrow receipts matched from bridge-outs (tight windows)",
            "amount_lpt": str(receipt_total),
            "events": receipt_events,
        },
        "numerator": {
            "basis": "those receipts routed to labeled exchange endpoints within window (best-effort)",
            "amount_lpt": str(exchange_total),
            "events": exchange_events,
        },
        "share_to_exchanges_lower_bound_percent": str(_pct(exchange_total, receipt_total)),
        "share_events_matched_percent": str(_pct(Decimal(exchange_events), Decimal(receipt_events))),
        "alternate_denominators": {
            "l2_withdraw_total": {"amount_lpt": str(withdraw_total), "events": withdraw_events},
            "share_to_exchanges_vs_l2_withdraw_percent": str(_pct(exchange_total, withdraw_total)),
        },
        "selection": {
            "senders_analyzed": senders_analyzed,
            "tight_window_params": {
                "withdraw_to_burn_hours": (params or {}).get("withdraw_to_burn_hours"),
                "burn_to_receipt_max_days": (params or {}).get("burn_to_receipt_max_days"),
                "receipt_to_firsthop_hours": (params or {}).get("receipt_to_firsthop_hours"),
                "firsthop_to_exchange_hours": (params or {}).get("firsthop_to_exchange_hours"),
                "min_receipt_forward_ratio": (params or {}).get("min_receipt_forward_ratio"),
            },
            "l2_block_range": {"from_block": (params or {}).get("l2_from_block"), "to_block": (params or {}).get("l2_to_block")},
            "l1_block_range": {"from_block": (params or {}).get("l1_from_block"), "to_block": (params or {}).get("l1_to_block")},
            "event_totals": {
                "burn_events": int((totals or {}).get("burn_events") or 0),
                "withdraw_events": int((totals or {}).get("withdraw_events") or 0),
                "matched_burn_to_receipt": matched_burn_to_receipt_events,
                "matched_receipt_to_exchange": matched_receipt_to_exchange_events,
            },
        },
        "labels": {"exchange_label_count": int(exchange_label_count) if isinstance(exchange_label_count, int) else None},
        "notes": [
            "This is a LOWER BOUND: it counts only transfers to a small curated set of labeled exchange hot wallets.",
            "Tight timing windows + hop limits miss slower or more complex routing paths.",
        ],
    }


def _filecoin_lock_burn_intensity_metrics(path: str) -> dict[str, Any]:
    data = _read_json(path)
    fc = data.get("filecoin") if isinstance(data, dict) else {}

    burnt = _d((fc or {}).get("burnt_funds_fil"))
    pledge = _d((fc or {}).get("power_total_pledge_collateral_fil"))
    daily_rewards = _d((fc or {}).get("daily_reward_estimate_fil"))

    burn_vs_pledge_ratio = (fc or {}).get("burn_vs_pledge_ratio")
    if burn_vs_pledge_ratio is None and pledge > 0:
        burn_vs_pledge_ratio = str(burnt / pledge)

    return {
        "source_json": path,
        "chain": "filecoin",
        "token": "FIL",
        "metric": "lock/burn intensity (context; not exchange-routing)",
        "snapshot": {"head_height": (fc or {}).get("head_height"), "rpc": (fc or {}).get("rpc")},
        "amounts": {
            "burnt_funds_fil": str(burnt),
            "power_total_pledge_collateral_fil": str(pledge),
            "daily_reward_estimate_fil": str(daily_rewards),
            "burn_vs_pledge_ratio": str(burn_vs_pledge_ratio) if burn_vs_pledge_ratio is not None else None,
        },
        "ratios": {
            "burn_equivalent_days_of_rewards": str(burnt / daily_rewards) if daily_rewards > 0 else None,
            "pledge_equivalent_days_of_rewards": str(pledge / daily_rewards) if daily_rewards > 0 else None,
        },
        "notes": [
            "This is not an exchange-routing metric; it’s a proxy for on-chain liquidity + penalty friction (burn sink + locked collateral).",
            "Actor balances and reward estimates are taken directly from the evidence pack JSON.",
        ],
    }


def _exit_friction_context(depin_snapshot_path: str, theta_liquidity_path: str) -> dict[str, Any]:
    snapshot = _read_json(depin_snapshot_path) if os.path.exists(depin_snapshot_path) else {}
    theta_pack = _read_json(theta_liquidity_path) if os.path.exists(theta_liquidity_path) else {}

    out: dict[str, Any] = {
        "sources": {"depin_snapshot_json": depin_snapshot_path, "theta_liquidity_json": theta_liquidity_path},
        "protocols": {},
        "notes": [
            "These are principal-liquidity exit delays / lock primitives (context). They are not equivalent to reward-only linear vesting.",
        ],
    }

    if isinstance(snapshot, dict):
        lp = snapshot.get("livepeer") or {}
        tg = snapshot.get("thegraph") or {}
        pocket = snapshot.get("pocket") or {}
        akash = snapshot.get("akash") or {}

        out["protocols"]["livepeer"] = {"unbonding_period_rounds": lp.get("unbonding_period_rounds")}
        out["protocols"]["thegraph"] = {"thawing_period_days_estimate": tg.get("thawing_period_days_estimate")}

        pocket_seconds = pocket.get("supplier_unbonding_seconds_estimate")
        pocket_days = float(pocket_seconds) / 86400 if pocket_seconds is not None else None
        out["protocols"]["pocket"] = {"supplier_unbonding_days_estimate": pocket_days}

        akash_seconds = akash.get("unbonding_time_seconds")
        akash_days = float(akash_seconds) / 86400 if akash_seconds is not None else None
        out["protocols"]["akash"] = {"unbonding_days_estimate": akash_days}

    if isinstance(theta_pack, dict):
        th = theta_pack.get("theta") or {}
        proto = th.get("protocol") or {}
        block_time = th.get("block_time_estimate") or {}

        return_blocks = _d(proto.get("return_locking_period_blocks"))
        avg_block_seconds = _d(block_time.get("avg_block_time_seconds"))

        nominal_days = (return_blocks * Decimal(6)) / Decimal(86400) if return_blocks > 0 else None
        observed_days = (return_blocks * avg_block_seconds) / Decimal(86400) if (return_blocks > 0 and avg_block_seconds > 0) else None

        out["protocols"]["theta"] = {
            "return_locking_period_blocks": int(return_blocks) if return_blocks > 0 else None,
            "return_locking_period_days_nominal_6s": str(nominal_days) if isinstance(nominal_days, Decimal) else None,
            "return_locking_period_days_observed": str(observed_days) if isinstance(observed_days, Decimal) else None,
        }

    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels-json", default="data/labels.json", help="EVM label set (used to count exchange labels).")
    parser.add_argument("--livepeer-l1-second-hop-json", default="research/l1-bridge-recipient-second-hop.json")
    parser.add_argument("--livepeer-extraction-timing-traces-json", default="research/extraction-timing-traces.json")
    parser.add_argument("--thegraph-withdrawal-routing-json", default="research/thegraph-delegation-withdrawal-routing.json")
    parser.add_argument("--curve-vecrv-exit-routing-json", default="research/curve-vecrv-exit-routing.json")
    parser.add_argument("--frax-vefxs-exit-routing-json", default="research/frax-vefxs-exit-routing.json")
    parser.add_argument("--aave-stkaave-redeem-exit-routing-json", default="research/aave-stkaave-redeem-exit-routing.json")
    parser.add_argument("--filecoin-lock-burn-metrics-json", default="research/filecoin-lock-burn-metrics.json")
    parser.add_argument("--depin-liquidity-primitives-snapshot-json", default="research/depin-liquidity-primitives-snapshot.json")
    parser.add_argument("--theta-liquidity-primitives-json", default="research/theta-liquidity-primitives.json")
    parser.add_argument("--out-json", default="research/exchange-routing-metrics.json")
    parser.add_argument("--out-md", default="research/exchange-routing-metrics.md")
    args = parser.parse_args()

    generated_at = datetime.now(tz=timezone.utc).isoformat()

    labels = _read_json(str(args.labels_json)) if os.path.exists(str(args.labels_json)) else {}
    exchange_label_count = _count_exchange_labels(labels) if isinstance(labels, dict) else 0

    livepeer = _livepeer_second_hop_metrics(str(args.livepeer_l1_second_hop_json), exchange_label_count=exchange_label_count)
    livepeer_tight = _livepeer_extraction_timing_traces_metrics(
        str(args.livepeer_extraction_timing_traces_json), exchange_label_count=exchange_label_count
    )
    thegraph = _thegraph_withdrawal_routing_metrics(str(args.thegraph_withdrawal_routing_json))
    curve = _erc20_exit_routing_metrics(str(args.curve_vecrv_exit_routing_json))
    frax = _erc20_exit_routing_metrics(str(args.frax_vefxs_exit_routing_json))
    aave = _erc20_exit_routing_metrics(str(args.aave_stkaave_redeem_exit_routing_json))
    filecoin = _filecoin_lock_burn_intensity_metrics(str(args.filecoin_lock_burn_metrics_json))
    exit_friction = _exit_friction_context(
        str(args.depin_liquidity_primitives_snapshot_json), str(args.theta_liquidity_primitives_json)
    )

    out = {
        "generated_at_utc": generated_at,
        "labels": {
            "labels_json": str(args.labels_json),
            "exchange_label_count": int(exchange_label_count),
            "notes": ["Label set is hand-curated and intentionally small; all routing shares are lower bounds."],
        },
        "metrics": {
            "livepeer_l1_second_hop": livepeer,
            "livepeer_extraction_timing_traces": livepeer_tight,
            "thegraph_delegation_withdrawal_routing": thegraph,
            "curve_vecrv_exit_routing": curve,
            "frax_vefxs_exit_routing": frax,
            "aave_stkaave_redeem_exit_routing": aave,
        },
        "context": {"filecoin_lock_burn_intensity": filecoin, "exit_friction_snapshot": exit_friction},
        "notes": [
            "All “exchange routing” metrics are best-effort and should be treated as LOWER BOUNDS.",
            "Different reports have different denominators (selection criteria and flow definitions); compare only with those caveats in mind.",
        ],
    }

    _write_json(str(args.out_json), out)

    # Markdown
    lp_ex = _d(livepeer["numerator"]["amount_lpt"])
    lp_total = _d(livepeer["denominator"]["amount_lpt"])
    lp_pct = _pct(lp_ex, lp_total)

    lt_ex = _d(livepeer_tight["numerator"]["amount_lpt"])
    lt_total = _d(livepeer_tight["denominator"]["amount_lpt"])
    lt_pct = _pct(lt_ex, lt_total)

    gr_ex = _d(thegraph["numerator"]["amount_grt"])
    gr_total = _d(thegraph["denominator"]["amount_grt"])
    gr_pct = _pct(gr_ex, gr_total)

    cv_ex = _d(curve["numerator"]["amount"])
    cv_total = _d(curve["denominator"]["amount"])
    cv_pct = _pct(cv_ex, cv_total)

    fx_ex = _d(frax["numerator"]["amount"])
    fx_total = _d(frax["denominator"]["amount"])
    fx_pct = _pct(fx_ex, fx_total)

    av_ex = _d(aave["numerator"]["amount"])
    av_total = _d(aave["denominator"]["amount"])
    av_pct = _pct(av_ex, av_total)

    ef = (exit_friction.get("protocols") or {}) if isinstance(exit_friction, dict) else {}
    lp_rounds = (ef.get("livepeer") or {}).get("unbonding_period_rounds")
    tg_days = (ef.get("thegraph") or {}).get("thawing_period_days_estimate")
    pocket_days = (ef.get("pocket") or {}).get("supplier_unbonding_days_estimate")
    akash_days = (ef.get("akash") or {}).get("unbonding_days_estimate")
    theta_days_observed = _d((ef.get("theta") or {}).get("return_locking_period_days_observed"))

    fc_amounts = (filecoin.get("amounts") or {}) if isinstance(filecoin, dict) else {}
    fc_ratios = (filecoin.get("ratios") or {}) if isinstance(filecoin, dict) else {}
    fc_burn = _d(fc_amounts.get("burnt_funds_fil"))
    fc_pledge = _d(fc_amounts.get("power_total_pledge_collateral_fil"))
    fc_daily = _d(fc_amounts.get("daily_reward_estimate_fil"))
    fc_burn_days = _d(fc_ratios.get("burn_equivalent_days_of_rewards"))
    fc_pledge_days = _d(fc_ratios.get("pledge_equivalent_days_of_rewards"))

    lines: list[str] = []
    lines.append("---")
    lines.append('title: "Exchange routing metrics (best-effort, on-chain)"')
    lines.append('description: "Standardized, lower-bound exchange-routing shares across Livepeer and comparable protocols."')
    lines.append('sidebar_label: "Exchange routing metrics"')
    lines.append("---")
    lines.append("")
    lines.append("# Exchange routing metrics (best-effort, on-chain)")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}`")
    lines.append(f"- Exchange label set size (EVM): **{exchange_label_count}** (`{args.labels_json}`)")
    lines.append("")
    lines.append("These metrics formalize the “X% goes to exchanges” claim as:")
    lines.append("- **numerator**: amount routed to a curated set of labeled exchange endpoints,")
    lines.append("- **denominator**: a clearly-defined post-exit flow basis (varies by report),")
    lines.append("- treated as a **LOWER BOUND** (labels + hop/window limits miss many paths).")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Protocol | Flow basis | Window / range | Hops | Routed to exchanges (lower bound) | Total basis | Share |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    # Livepeer row
    lp_rng = livepeer["selection"]["block_range"]
    lp_range_str = f"{lp_rng.get('from_block')}→{lp_rng.get('to_block')}"
    lines.append(
        f"| Livepeer (LPT) | selected L1 EOA outgoing (2nd hop) | blocks {lp_range_str} | 1 | {lp_ex:.3f} LPT | {lp_total:.3f} LPT | {_fmt_pct(lp_pct)} |"
    )
    # Livepeer (tight-window traces) row
    lt_params = livepeer_tight["selection"]["tight_window_params"]
    lt_window = f"≤{lt_params.get('receipt_to_firsthop_hours')}h→≤{lt_params.get('firsthop_to_exchange_hours')}h"
    lines.append(
        f"| Livepeer (LPT) | L1 receipts from traced bridge-outs | {lt_window} | ≤2 | {lt_ex:.3f} LPT | {lt_total:.3f} LPT | {_fmt_pct(lt_pct)} |"
    )
    # Graph row
    gr_win = thegraph["selection"]["window_days"]
    gr_hops = 3
    lines.append(
        f"| The Graph (GRT) | withdrawals (top delegators) | {gr_win}d window | ≤{gr_hops} | {gr_ex:.3f} GRT | {gr_total:.3f} GRT | {_fmt_pct(gr_pct)} |"
    )
    # Curve row
    cv_win = curve["selection"]["window_days"]
    lines.append(
        f"| Curve (CRV) | veCRV withdraws (top recipients) | {cv_win}d window | ≤3 | {cv_ex:.3f} CRV | {cv_total:.3f} CRV | {_fmt_pct(cv_pct)} |"
    )
    # Frax row
    fx_win = frax["selection"]["window_days"]
    lines.append(
        f"| Frax (FXS) | veFXS withdraws (top recipients) | {fx_win}d window | ≤3 | {fx_ex:.3f} FXS | {fx_total:.3f} FXS | {_fmt_pct(fx_pct)} |"
    )
    # Aave row
    av_win = aave["selection"]["window_days"]
    lines.append(
        f"| Aave (AAVE) | stkAAVE redeem (top recipients) | {av_win}d window | ≤3 | {av_ex:.3f} AAVE | {av_total:.3f} AAVE | {_fmt_pct(av_pct)} |"
    )
    lines.append("")
    lines.append("## First hop destinations (where available)")
    lines.append("")
    lines.append("These breakdowns answer a different question than “eventual exchange deposit”:")
    lines.append("- **Where does the *first* large post-exit transfer go?**")
    lines.append("")
    lines.append("They are useful to quantify “self-custody / unknown EOA” vs known endpoints, but they are **not apples-to-apples** across reports.")
    lines.append("")
    lines.append("| Protocol | Basis | Unknown EOA | Unknown contract | No first hop meeting threshold |")
    lines.append("|---|---|---:|---:|---:|")

    lp_unknown = _d(livepeer.get("share_to_unknown_eoas_percent"))
    lines.append(f"| Livepeer (LPT) | 2nd hop from selected L1 EOAs | {_fmt_pct(lp_unknown)} |  |  |")

    gr_fh = (thegraph.get("first_hop_destinations") or {}) if isinstance(thegraph, dict) else {}
    gr_fh_shares = (gr_fh.get("category_withdrawn_share_percent") or {}) if isinstance(gr_fh, dict) else {}
    gr_unk_eoa = _d(gr_fh_shares.get("unknown_eoa"))
    gr_unk_contract = _d(gr_fh_shares.get("unknown_contract"))
    gr_no_first = _d(gr_fh_shares.get("no_first_hop_meeting_threshold"))
    lines.append(
        f"| The Graph (GRT) | 1st hop after withdrawal (thresholded) | {_fmt_pct(gr_unk_eoa)} | {_fmt_pct(gr_unk_contract)} | {_fmt_pct(gr_no_first)} |"
    )

    cv_fh = (curve.get("first_hop_destinations") or {}) if isinstance(curve, dict) else {}
    cv_fh_shares = (cv_fh.get("category_exit_share_percent") or {}) if isinstance(cv_fh, dict) else {}
    cv_unk_eoa = _d(cv_fh_shares.get("unknown_eoa"))
    cv_unk_contract = _d(cv_fh_shares.get("unknown_contract"))
    cv_no_first = _d(cv_fh_shares.get("no_first_hop_meeting_threshold"))
    lines.append(f"| Curve (CRV) | 1st hop after veCRV withdraw (thresholded) | {_fmt_pct(cv_unk_eoa)} | {_fmt_pct(cv_unk_contract)} | {_fmt_pct(cv_no_first)} |")

    fx_fh = (frax.get("first_hop_destinations") or {}) if isinstance(frax, dict) else {}
    fx_fh_shares = (fx_fh.get("category_exit_share_percent") or {}) if isinstance(fx_fh, dict) else {}
    fx_unk_eoa = _d(fx_fh_shares.get("unknown_eoa"))
    fx_unk_contract = _d(fx_fh_shares.get("unknown_contract"))
    fx_no_first = _d(fx_fh_shares.get("no_first_hop_meeting_threshold"))
    lines.append(f"| Frax (FXS) | 1st hop after veFXS withdraw (thresholded) | {_fmt_pct(fx_unk_eoa)} | {_fmt_pct(fx_unk_contract)} | {_fmt_pct(fx_no_first)} |")

    av_fh = (aave.get("first_hop_destinations") or {}) if isinstance(aave, dict) else {}
    av_fh_shares = (av_fh.get("category_exit_share_percent") or {}) if isinstance(av_fh, dict) else {}
    av_unk_eoa = _d(av_fh_shares.get("unknown_eoa"))
    av_unk_contract = _d(av_fh_shares.get("unknown_contract"))
    av_no_first = _d(av_fh_shares.get("no_first_hop_meeting_threshold"))
    lines.append(f"| Aave (AAVE) | 1st hop after stkAAVE redeem (thresholded) | {_fmt_pct(av_unk_eoa)} | {_fmt_pct(av_unk_contract)} | {_fmt_pct(av_no_first)} |")

    lines.append("")
    lines.append("## Notes (how to interpret)")
    lines.append("")
    lines.append("- These shares are **not directly comparable** unless you account for the denominator differences (selection rules, hop limits, and windows).")
    lines.append("- Best use: track *directionally* whether “post-exit flows” are consistent with eventual exchange deposits.")
    lines.append("")
    lines.append("## Context (exit friction + lock/burn primitives)")
    lines.append("")
    lines.append("Exit friction (principal liquidity delays; not reward vesting):")
    lines.append("")
    lines.append("| Protocol | Primitive | Delay (estimate) |")
    lines.append("|---|---|---:|")
    lines.append(f"| Livepeer | `unbondingPeriod()` | {lp_rounds} rounds |")
    lines.append(
        f"| The Graph | `thawingPeriod()` | ~{float(tg_days):.1f} days |" if tg_days is not None else "| The Graph | `thawingPeriod()` |  |"
    )
    lines.append(
        f"| Pocket | supplier unbonding | ~{float(pocket_days):.1f} days |"
        if pocket_days is not None
        else "| Pocket | supplier unbonding |  |"
    )
    lines.append(f"| Akash | `unbonding_time` | ~{float(akash_days):.1f} days |" if akash_days is not None else "| Akash | `unbonding_time` |  |")
    lines.append(
        f"| Theta | `ReturnLockingPeriod` | ~{float(theta_days_observed):.1f} days |"
        if theta_days_observed > 0
        else "| Theta | `ReturnLockingPeriod` |  |"
    )
    lines.append("")
    lines.append("Filecoin lock/burn intensity (on-chain friction; not exchange routing):")
    lines.append("")
    lines.append(
        f"- Burnt funds: **{fc_burn:.3f} FIL** (~{fc_burn_days:.0f} days of rewards @ {fc_daily:.3f} FIL/day)"
        if (fc_burn > 0 and fc_daily > 0 and fc_burn_days > 0)
        else f"- Burnt funds: **{fc_burn:.3f} FIL**"
    )
    lines.append(
        f"- Pledge collateral locked: **{fc_pledge:.3f} FIL** (~{fc_pledge_days:.0f} days of rewards)"
        if (fc_pledge > 0 and fc_daily > 0 and fc_pledge_days > 0)
        else f"- Pledge collateral locked: **{fc_pledge:.3f} FIL**"
    )
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    lines.append(f"- Livepeer L1 second hop JSON: `{args.livepeer_l1_second_hop_json}`")
    lines.append(f"- Livepeer timing traces JSON: `{args.livepeer_extraction_timing_traces_json}`")
    lines.append(f"- The Graph withdrawal routing JSON: `{args.thegraph_withdrawal_routing_json}`")
    lines.append(f"- Curve veCRV exit routing JSON: `{args.curve_vecrv_exit_routing_json}`")
    lines.append(f"- Frax veFXS exit routing JSON: `{args.frax_vefxs_exit_routing_json}`")
    lines.append(f"- Aave stkAAVE redeem exit routing JSON: `{args.aave_stkaave_redeem_exit_routing_json}`")
    lines.append(f"- Filecoin lock/burn JSON: `{args.filecoin_lock_burn_metrics_json}`")
    lines.append(f"- DePIN exit-friction snapshot JSON: `{args.depin_liquidity_primitives_snapshot_json}`")
    lines.append(f"- Theta liquidity primitives JSON: `{args.theta_liquidity_primitives_json}`")
    lines.append("")
    lines.append("Raw output: see `research/exchange-routing-metrics.json`.")

    _write_text(str(args.out_md), "\n".join(lines) + "\n")

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
