#!/usr/bin/env python3
"""
Delegate outflow profile: top unbonders + claimed earnings vs WithdrawStake cashout (Arbitrum).

Answers:
- Who are the top unbonders (by LPT) from a given delegate/orchestrator address?
- For each wallet, how much did they claim in staking rewards/fees and how much did they
  withdraw from BondingManager (cashout into LPT tokens)?

Important notes:
- `Unbond` is not a clean exit; stake can later be `Rebond`ed.
- `WithdrawStake` is a cashout of unlocked stake and can include principal + rewards,
  so `WithdrawStake / (rewards+fees)` ratios are only a coarse indicator.

Inputs come from the main workspace scan artifacts:
- `unbond_events.ndjson` (event-level Unbond rows)
- `delegators_state.pkl` (per-wallet aggregates across all events)

Optional:
- An RPC snapshot of each wallet's current `bondedAmount` and current `delegateAddress`
  at a stable snapshot block, via `BondingManager.getDelegator(address)`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 50

ARBITRUM_PUBLIC_RPC = "https://arb1.arbitrum.io/rpc"
LIVEPEER_BONDING_MANAGER = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"

# getDelegator(address) selector: 0xa64ad595
GET_DELEGATOR_SELECTOR = "a64ad595"

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS


class RpcError(RuntimeError):
    pass


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 45):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s

    def call_raw(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "livepeer-research/delegate_unbonders_cashout"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except HTTPError as e:
            raise RpcError(f"HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            raise RpcError(f"URL error: {e.reason}") from e
        except Exception as e:
            raise RpcError(f"RPC transport error: {e}") from e
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise RpcError(f"invalid JSON-RPC response: {raw[:200]!r}") from e


def _rpc_with_retries(fn, *, max_tries: int = 8) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return fn()
        except RpcError as e:
            msg = str(e).lower()
            retryable = any(s in msg for s in ("timeout", "too many requests", "rate limit", "service unavailable", "bad gateway"))
            if not retryable or attempt == max_tries:
                raise
            time.sleep(min(2 ** (attempt - 1), 30))


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _format_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def _call_data_get_delegator(addr: str) -> str:
    a = _normalize_address(addr)
    return "0x" + GET_DELEGATOR_SELECTOR + ("0" * 24) + a[2:]


def _parse_get_delegator_output(out: str) -> Tuple[int, str]:
    if not isinstance(out, str) or not out.startswith("0x"):
        raise ValueError("invalid eth_call output")
    hex_data = out[2:]
    if len(hex_data) < 64 * 3:
        raise ValueError("short getDelegator output")
    bonded_amount = int(hex_data[0:64], 16)
    delegate_slot = hex_data[128:192]
    delegate_addr = "0x" + delegate_slot[24:64]
    return bonded_amount, delegate_addr.lower()


def _write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


@dataclass(frozen=True)
class WalletRow:
    address: str
    unbond_from_delegate_lpt: Decimal
    rewards_claimed_lpt: Decimal
    fees_claimed_lpt: Decimal
    withdraw_total_lpt: Decimal
    claim_events: int
    withdraw_events: int
    bonded_now_lpt: Optional[Decimal]
    current_delegate: Optional[str]

    @property
    def claimed_total_lpt(self) -> Decimal:
        return self.rewards_claimed_lpt + self.fees_claimed_lpt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delegate", required=True)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument(
        "--unbond-events-ndjson",
        default=os.path.join("..", "..", "artifacts", "livepeer-bm-scan-arbitrum-v2", "unbond_events.ndjson"),
    )
    parser.add_argument(
        "--delegators-state-pkl",
        default=os.path.join("..", "..", "artifacts", "livepeer-bm-scan-arbitrum-v2", "delegators_state.pkl"),
    )
    parser.add_argument("--rpc-url", default=ARBITRUM_PUBLIC_RPC)
    parser.add_argument("--bonding-manager", default=LIVEPEER_BONDING_MANAGER)
    parser.add_argument("--block-lag", type=int, default=200)
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--out-md", default=None)
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args()

    delegate = _normalize_address(args.delegate)
    top_n = max(1, int(args.top_n))
    slug = delegate[2:10]

    out_md = args.out_md or f"research/delegate-{slug}-top-unbonders.md"
    out_json = args.out_json or f"research/delegate-{slug}-top-unbonders.json"

    # 1) Aggregate Unbond events for this delegate
    by_delegator_wei: Dict[str, int] = {}
    total_unbond_wei = 0
    total_events = 0

    with open(args.unbond_events_ndjson, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            if str(o.get("delegate", "")).lower() != delegate:
                continue
            delegator = _normalize_address(o["delegator"])
            amt = int(o["amount"])
            total_unbond_wei += amt
            total_events += 1
            by_delegator_wei[delegator] = by_delegator_wei.get(delegator, 0) + amt

    ranked = sorted(by_delegator_wei.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:top_n]

    def share_of_top(k: int) -> float:
        if total_unbond_wei <= 0:
            return 0.0
        s = sum(v for _a, v in ranked[:k])
        return float(Decimal(s) / Decimal(total_unbond_wei))

    top1_share = share_of_top(1)
    top5_share = share_of_top(5)
    top10_share = share_of_top(10)

    # 2) Load per-wallet aggregates
    with open(args.delegators_state_pkl, "rb") as f:
        state = pickle.load(f)
    delegators_state = state.get("delegators")
    if not isinstance(delegators_state, dict):
        raise SystemExit("delegators_state.pkl missing 'delegators' dict")

    # 3) Optional snapshot: current bondedAmount + delegateAddress for the top wallets
    snapshot_meta: Optional[Dict[str, Any]] = None
    snapshot_by_addr: Dict[str, Tuple[int, str]] = {}
    if not args.no_snapshot and top:
        rpc = RpcClient(args.rpc_url)
        latest_block_hex = _rpc_with_retries(lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}))
        if not isinstance(latest_block_hex, dict) or not isinstance(latest_block_hex.get("result"), str):
            raise RpcError(f"unexpected eth_blockNumber response: {latest_block_hex!r}")
        latest_block = int(latest_block_hex["result"], 16)
        snapshot_block = max(0, latest_block - max(0, int(args.block_lag)))
        block_tag = hex(snapshot_block)

        block = _rpc_with_retries(
            lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber", "params": [block_tag, False]})
        )
        if not isinstance(block, dict) or not isinstance(block.get("result"), dict):
            raise RpcError(f"unexpected eth_getBlockByNumber response: {block!r}")
        snapshot_ts = int(block["result"]["timestamp"], 16)

        payload = []
        id_to_addr: Dict[int, str] = {}
        req_id = 1000
        for addr, _amt in top:
            call_obj = {"to": args.bonding_manager, "data": _call_data_get_delegator(addr)}
            payload.append({"jsonrpc": "2.0", "id": req_id, "method": "eth_call", "params": [call_obj, block_tag]})
            id_to_addr[req_id] = addr
            req_id += 1

        resp = _rpc_with_retries(lambda: rpc.call_raw(payload))
        if not isinstance(resp, list):
            raise RpcError(f"unexpected batch response type: {type(resp)}")
        for item in resp:
            if not isinstance(item, dict) or "id" not in item:
                continue
            addr = id_to_addr.get(item.get("id"))
            if not addr:
                continue
            if item.get("error"):
                raise RpcError(f"eth_call error for {addr}: {item['error']}")
            result = item.get("result")
            bonded_amount, current_delegate = _parse_get_delegator_output(result)
            snapshot_by_addr[addr] = (bonded_amount, current_delegate)

        snapshot_meta = {
            "rpc_url": args.rpc_url,
            "bonding_manager": str(args.bonding_manager).lower(),
            "latest_block_at_start": latest_block,
            "snapshot_block": snapshot_block,
            "snapshot_block_timestamp": snapshot_ts,
            "block_lag": int(args.block_lag),
        }

    # 4) Join tables for the top wallets
    rows: List[WalletRow] = []
    for addr, unbond_wei in top:
        e = delegators_state.get(addr)
        if not isinstance(e, dict):
            continue
        rewards = _wei_to_lpt(int(e.get("total_rewards_claimed") or 0))
        fees = _wei_to_lpt(int(e.get("total_fees_claimed") or 0))
        withdraw = _wei_to_lpt(int(e.get("total_withdraw_amount") or 0))
        claim_events = int(e.get("earnings_claim_events") or 0)
        withdraw_events = int(e.get("withdraw_events") or 0)

        bonded_now_lpt: Optional[Decimal] = None
        current_delegate: Optional[str] = None
        if snapshot_meta is not None:
            bonded_now_wei, current_delegate = snapshot_by_addr.get(addr, (0, "0x" + "0" * 40))
            bonded_now_lpt = _wei_to_lpt(bonded_now_wei)

        rows.append(
            WalletRow(
                address=addr,
                unbond_from_delegate_lpt=_wei_to_lpt(unbond_wei),
                rewards_claimed_lpt=rewards,
                fees_claimed_lpt=fees,
                withdraw_total_lpt=withdraw,
                claim_events=claim_events,
                withdraw_events=withdraw_events,
                bonded_now_lpt=bonded_now_lpt,
                current_delegate=current_delegate,
            )
        )

    out_payload: Dict[str, Any] = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "delegate": delegate,
            "top_n": top_n,
            "unbond_events_ndjson": args.unbond_events_ndjson,
            "delegators_state_pkl": args.delegators_state_pkl,
        },
        "unbond_summary": {
            "total_unbond_lpt": str(_wei_to_lpt(total_unbond_wei)),
            "unbond_events": total_events,
            "unique_unbonders": len(by_delegator_wei),
            "top1_share_of_unbond_amount": top1_share,
            "top5_share_of_unbond_amount": top5_share,
            "top10_share_of_unbond_amount": top10_share,
        },
        "snapshot": snapshot_meta,
        "top_unbonders": [
            {
                "delegator": r.address,
                "unbond_from_delegate_lpt": str(r.unbond_from_delegate_lpt),
                "rewards_claimed_lpt": str(r.rewards_claimed_lpt),
                "fees_claimed_lpt": str(r.fees_claimed_lpt),
                "claimed_total_lpt": str(r.claimed_total_lpt),
                "withdraw_total_lpt": str(r.withdraw_total_lpt),
                "claim_events": r.claim_events,
                "withdraw_events": r.withdraw_events,
                "bonded_now_lpt": str(r.bonded_now_lpt) if r.bonded_now_lpt is not None else None,
                "current_delegate": r.current_delegate,
                "bonded_to_target_now": (r.current_delegate == delegate) if r.current_delegate else None,
            }
            for r in rows
        ],
    }
    _write_json_atomic(out_json, out_payload)

    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(f"# Delegate profile — `{delegate}`\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Unbond events: `{total_events:,}`\n")
        f.write(f"- Unique unbonders: `{len(by_delegator_wei):,}`\n")
        f.write(f"- Total unbonded from this delegate: `{_format_lpt(_wei_to_lpt(total_unbond_wei))} LPT`\n")
        f.write(f"- Concentration (share of unbonded LPT): top1 `{_format_pct(top1_share)}`, top5 `{_format_pct(top5_share)}`, top10 `{_format_pct(top10_share)}`\n\n")

        if snapshot_meta is not None:
            f.write("## Snapshot (current state)\n\n")
            f.write(f"- Latest block at start: `{snapshot_meta['latest_block_at_start']}`\n")
            f.write(f"- Snapshot block: `{snapshot_meta['snapshot_block']}` (lag `{snapshot_meta['block_lag']}`) — {_iso(int(snapshot_meta['snapshot_block_timestamp']))}\n\n")

        f.write("## Top unbonders (by total unbonded from this delegate)\n\n")
        f.write("| # | Delegator | Unbonded from delegate | Claimed rewards | Claimed fees | Claimed total | WithdrawStake total | Withdraw/claimed | Bonded now | Current delegate |\n")
        f.write("|---:|---|---:|---:|---:|---:|---:|---:|---:|---|\n")
        for i, r in enumerate(rows, start=1):
            claimed = r.claimed_total_lpt
            ratio = float(r.withdraw_total_lpt / claimed) if claimed > 0 else math.nan
            ratio_fmt = f"{ratio*100:.1f}%" if not math.isnan(ratio) else "n/a"
            bonded_now = r.bonded_now_lpt if r.bonded_now_lpt is not None else Decimal(0)
            current_delegate = r.current_delegate or "n/a"
            f.write(
                f"| {i} | `{r.address}` | {_format_lpt(r.unbond_from_delegate_lpt)} | {_format_lpt(r.rewards_claimed_lpt)} | {_format_lpt(r.fees_claimed_lpt)} | {_format_lpt(claimed)} | {_format_lpt(r.withdraw_total_lpt)} | {ratio_fmt} | {_format_lpt(bonded_now)} | `{current_delegate}` |\n"
            )

        f.write("\n## Notes\n\n")
        f.write("- `Unbond` is not a clean exit; stake can later be rebonded.\n")
        f.write("- `WithdrawStake` is a cashout of unlocked stake and can include principal + rewards.\n")
        f.write("- `Withdraw/claimed` > 100% typically indicates the wallet withdrew principal in addition to any earned stake.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

