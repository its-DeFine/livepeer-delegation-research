#!/usr/bin/env python3
"""
Livepeer Arbitrum — rewards vs withdraw time series (event scan via eth_getLogs).

Motivation
----------
When evaluating claims like “delta-neutral yield extraction creates structural sell pressure”,
we need *time-series* evidence for:
- rewards claimed (EarningsClaimed.rewards) and
- stake withdrawn (WithdrawStake.amount)

We avoid archive requirements by using eth_getLogs. To bucket events into months without
per-log block timestamp lookups, we use the month-end snapshot blocks already present in
`research/delegator-band-timeseries.json` (produced by event replay).

Outputs
-------
- research/rewards-withdraw-timeseries.md
- research/rewards-withdraw-timeseries.json

Notes
-----
- Rewards are *claimed rewards* (not necessarily all rewards accrued but unclaimed).
- WithdrawStake is the LPT withdrawn after unbonding lock maturity.
- This script is stdlib-only and supports resumability via a pickle state file.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

ARBITRUM_PUBLIC_RPC = "https://arb1.arbitrum.io/rpc"
LIVEPEER_BONDING_MANAGER = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"

# cast sig-event "WithdrawStake(address,uint256,uint256)"
TOPIC0_WITHDRAW_STAKE = "0x1340f1a8f3d456a649e1a12071dfa15655e3d09252131d0f980c3b405cc8dd2e"
# cast sig-event "EarningsClaimed(address,address,uint256,uint256,uint256,uint256)"
TOPIC0_EARNINGS_CLAIMED = "0xd7eab0765b772ea6ea859d5633baf737502198012e930f257f90013d9b211094"

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS


class RpcError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 45):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self._id = 0

    def call(self, method: str, params: list) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "livepeer-delegation-research/rewards_withdraw_timeseries"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except HTTPError as e:
            retry_after_s: int | None = None
            try:
                ra = e.headers.get("Retry-After")
                if isinstance(ra, str) and ra.strip().isdigit():
                    retry_after_s = int(ra.strip())
            except Exception:
                retry_after_s = None
            raise RpcError(
                f"HTTP {e.code}: {e.reason}",
                status_code=int(getattr(e, "code", 0)) or None,
                retry_after_s=retry_after_s,
            ) from e
        except URLError as e:
            raise RpcError(f"URL error: {e.reason}") from e
        except Exception as e:
            raise RpcError(f"RPC transport error: {e}") from e

        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise RpcError(f"invalid JSON-RPC response: {raw[:200]!r}") from e

        if isinstance(data, dict) and data.get("error"):
            raise RpcError(str(data["error"]))
        return data.get("result") if isinstance(data, dict) else data


def _rpc_with_retries(client: RpcClient, method: str, params: list, *, max_tries: int = 8) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return client.call(method, params)
        except RpcError as e:
            msg = str(e).lower()
            retryable_http = getattr(e, "status_code", None) in (429, 502, 503, 504)
            retryable = any(
                s in msg
                for s in (
                    "timeout",
                    "timed out",
                    "too many requests",
                    "rate limit",
                    "temporarily unavailable",
                    "service unavailable",
                    "bad gateway",
                    "gateway timeout",
                    "connection reset",
                    "internal error",
                )
            )
            if (not retryable and not retryable_http) or attempt == max_tries:
                raise

            sleep_s = min(2 ** (attempt - 1), 30.0)
            retry_after_s = getattr(e, "retry_after_s", None)
            if isinstance(retry_after_s, int) and retry_after_s > 0:
                sleep_s = max(sleep_s, float(retry_after_s))
            sleep_s = sleep_s * (1 + random.uniform(-0.15, 0.15))
            time.sleep(max(0.5, sleep_s))


def _decode_words(data_hex: str, n: int) -> List[int]:
    if not data_hex.startswith("0x"):
        raise ValueError("data must be 0x-prefixed")
    hex_str = data_hex[2:]
    need = 64 * n
    if len(hex_str) < need:
        raise ValueError(f"data too short: need {need} hex chars, got {len(hex_str)}")
    return [int(hex_str[i : i + 64], 16) for i in range(0, need, 64)]


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _get_logs(client: RpcClient, *, address: str, topic0_any_of: List[str], from_block: int, to_block: int) -> List[Dict[str, Any]]:
    return _rpc_with_retries(
        client,
        "eth_getLogs",
        [
            {
                "address": address,
                "fromBlock": hex(int(from_block)),
                "toBlock": hex(int(to_block)),
                "topics": [topic0_any_of],
            }
        ],
    )


def _get_logs_range(
    client: RpcClient,
    *,
    address: str,
    topic0_any_of: List[str],
    from_block: int,
    to_block: int,
    max_splits: int = 18,
) -> List[Dict[str, Any]]:
    try:
        return _get_logs(client, address=address, topic0_any_of=topic0_any_of, from_block=from_block, to_block=to_block)
    except RpcError as e:
        msg = str(e).lower()
        too_many = any(
            s in msg
            for s in (
                "more than",
                "too many results",
                "response size exceeded",
                "query returned more than",
                "block range too wide",
            )
        )
        if not too_many or max_splits <= 0 or from_block >= to_block:
            raise
        mid = (from_block + to_block) // 2
        left = _get_logs_range(
            client,
            address=address,
            topic0_any_of=topic0_any_of,
            from_block=from_block,
            to_block=mid,
            max_splits=max_splits - 1,
        )
        right = _get_logs_range(
            client,
            address=address,
            topic0_any_of=topic0_any_of,
            from_block=mid + 1,
            to_block=to_block,
            max_splits=max_splits - 1,
        )
        return left + right


def _month_key_from_iso(iso: str) -> str:
    # ISO like "2024-12-31T23:59:59+00:00" -> "2024-12"
    s = str(iso)
    if len(s) < 7:
        return "unknown"
    return s[:7]


def _load_month_boundaries(timeseries_json: str) -> List[Tuple[int, str, str]]:
    ts = json.load(open(timeseries_json, "r", encoding="utf-8"))
    snaps = ts.get("snapshots") or []
    if not isinstance(snaps, list) or not snaps:
        raise SystemExit(f"bad timeseries json: {timeseries_json}")

    out: List[Tuple[int, str, str]] = []
    last_block = -1
    for s in snaps:
        b = int(s.get("snapshot_block") or 0)
        iso = str(s.get("snapshot_iso") or "")
        label = str(s.get("label") or "")
        if b <= 0 or not iso:
            continue
        if b <= last_block:
            continue
        month_key = _month_key_from_iso(iso)
        out.append((b, month_key, label))
        last_block = b
    if not out:
        raise SystemExit(f"no usable snapshot boundaries in: {timeseries_json}")
    return out


@dataclass
class ScanState:
    version: int
    rpc_url: str
    bonding_manager: str
    from_block: int
    to_block: int
    chunk_size: int
    next_block: int
    # month_key -> {rewards_wei, withdraw_wei, claim_events, withdraw_events}
    months: Dict[str, Dict[str, int]]
    updated_at_utc: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", default=ARBITRUM_PUBLIC_RPC)
    parser.add_argument("--bonding-manager", default=LIVEPEER_BONDING_MANAGER)
    parser.add_argument("--timeseries-json", default="research/delegator-band-timeseries.json")
    parser.add_argument("--from-block", type=int, default=5856381)
    parser.add_argument("--to-block", type=int, default=0, help="0 = latest snapshot block from --timeseries-json")
    parser.add_argument("--chunk-size", type=int, default=10_000_000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--state-pkl", default="artifacts/rewards_withdraw_timeseries_state.pkl")
    parser.add_argument("--out-md", default="research/rewards-withdraw-timeseries.md")
    parser.add_argument("--out-json", default="research/rewards-withdraw-timeseries.json")
    args = parser.parse_args()

    boundaries = _load_month_boundaries(str(args.timeseries_json))
    # Last boundary is typically "latest".
    latest_block = boundaries[-1][0]

    from_block = int(args.from_block)
    to_block = int(args.to_block) or int(latest_block)
    if from_block >= to_block:
        raise SystemExit(f"from_block {from_block} >= to_block {to_block}")

    client = RpcClient(str(args.rpc_url))

    state: ScanState | None = None
    if args.resume and os.path.exists(args.state_pkl):
        with open(args.state_pkl, "rb") as f:
            raw = pickle.load(f)
        if isinstance(raw, ScanState):
            state = raw

    if state is None:
        state = ScanState(
            version=1,
            rpc_url=str(args.rpc_url),
            bonding_manager=_normalize_address(args.bonding_manager),
            from_block=from_block,
            to_block=to_block,
            chunk_size=int(args.chunk_size),
            next_block=from_block,
            months={},
            updated_at_utc=datetime.now(tz=timezone.utc).isoformat(),
        )
        os.makedirs(os.path.dirname(args.state_pkl), exist_ok=True)
        with open(args.state_pkl, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)

    if state.bonding_manager != _normalize_address(args.bonding_manager):
        raise SystemExit("state-pkl bonding_manager mismatch; delete state or pass matching --bonding-manager")

    def save_state() -> None:
        state.updated_at_utc = datetime.now(tz=timezone.utc).isoformat()
        tmp = args.state_pkl + ".tmp"
        os.makedirs(os.path.dirname(args.state_pkl), exist_ok=True)
        with open(tmp, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, args.state_pkl)

    # Month boundary cursor
    boundary_idx = 0
    boundary_block = boundaries[boundary_idx][0]
    boundary_month = boundaries[boundary_idx][1]

    def month_for_block(block_number: int) -> str:
        nonlocal boundary_idx, boundary_block, boundary_month
        while boundary_idx < len(boundaries) - 1 and block_number > boundary_block:
            boundary_idx += 1
            boundary_block = boundaries[boundary_idx][0]
            boundary_month = boundaries[boundary_idx][1]
        return boundary_month

    def touch_month(key: str) -> Dict[str, int]:
        if key not in state.months:
            state.months[key] = {"rewards_wei": 0, "withdraw_wei": 0, "claim_events": 0, "withdraw_events": 0}
        return state.months[key]

    topic0_any = [TOPIC0_EARNINGS_CLAIMED, TOPIC0_WITHDRAW_STAKE]

    while state.next_block <= state.to_block:
        chunk_from = int(state.next_block)
        chunk_to = min(int(state.to_block), chunk_from + int(state.chunk_size) - 1)

        logs = _get_logs_range(
            client,
            address=state.bonding_manager,
            topic0_any_of=topic0_any,
            from_block=chunk_from,
            to_block=chunk_to,
        )

        for log in logs:
            topics = log.get("topics") or []
            if not topics:
                continue
            topic0 = str(topics[0]).lower()
            block_number = int(log.get("blockNumber", "0x0"), 16)
            if block_number <= 0:
                continue
            data_hex = str(log.get("data") or "0x")
            m = month_for_block(block_number)
            row = touch_month(m)

            if topic0 == TOPIC0_EARNINGS_CLAIMED:
                rewards_wei, _fees_wei, _start_round, _end_round = _decode_words(data_hex, 4)
                row["rewards_wei"] += int(rewards_wei)
                row["claim_events"] += 1
            elif topic0 == TOPIC0_WITHDRAW_STAKE:
                _lock_id, amount_wei, _withdraw_round = _decode_words(data_hex, 3)
                row["withdraw_wei"] += int(amount_wei)
                row["withdraw_events"] += 1

        state.next_block = chunk_to + 1
        save_state()

        print(f"scanned {chunk_from:,}..{chunk_to:,} ({len(logs):,} logs)")

    # Compose output (sorted by month key)
    by_month: Dict[str, Dict[str, Any]] = {}
    total_rewards_wei = 0
    total_withdraw_wei = 0
    total_claim_events = 0
    total_withdraw_events = 0

    for m in sorted(state.months.keys()):
        row = state.months[m]
        rw = int(row.get("rewards_wei") or 0)
        ww = int(row.get("withdraw_wei") or 0)
        ce = int(row.get("claim_events") or 0)
        we = int(row.get("withdraw_events") or 0)
        total_rewards_wei += rw
        total_withdraw_wei += ww
        total_claim_events += ce
        total_withdraw_events += we
        by_month[m] = {
            "rewards_lpt": str(_wei_to_lpt(rw)),
            "withdraw_lpt": str(_wei_to_lpt(ww)),
            "claim_events": ce,
            "withdraw_events": we,
        }

    by_year: Dict[str, Dict[str, Any]] = {}
    for m, row in by_month.items():
        year = m[:4] if len(m) >= 4 else "unknown"
        if year not in by_year:
            by_year[year] = {"rewards_lpt": "0", "withdraw_lpt": "0", "claim_events": 0, "withdraw_events": 0}
        y = by_year[year]
        y["rewards_lpt"] = str(Decimal(y["rewards_lpt"]) + Decimal(row["rewards_lpt"]))
        y["withdraw_lpt"] = str(Decimal(y["withdraw_lpt"]) + Decimal(row["withdraw_lpt"]))
        y["claim_events"] = int(y["claim_events"]) + int(row["claim_events"])
        y["withdraw_events"] = int(y["withdraw_events"]) + int(row["withdraw_events"])

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "rpc_url": state.rpc_url,
        "bonding_manager": state.bonding_manager,
        "timeseries_boundaries_json": str(args.timeseries_json),
        "range": {"from_block": state.from_block, "to_block": state.to_block},
        "totals": {
            "rewards_lpt": str(_wei_to_lpt(total_rewards_wei)),
            "withdraw_lpt": str(_wei_to_lpt(total_withdraw_wei)),
            "claim_events": total_claim_events,
            "withdraw_events": total_withdraw_events,
        },
        "by_year": {k: by_year[k] for k in sorted(by_year.keys())},
        "by_month": by_month,
    }

    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, sort_keys=True)
        f.write("\n")

    # Markdown
    lines: List[str] = []
    lines.append("# Livepeer Arbitrum — Rewards claimed vs stake withdrawn (time series)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- RPC: `{out_json['rpc_url']}`")
    lines.append(f"- BondingManager: `{out_json['bonding_manager']}`")
    lines.append(f"- Range: `{out_json['range']['from_block']}` → `{out_json['range']['to_block']}`")
    lines.append(f"- Totals: rewards `{_format_lpt(Decimal(out_json['totals']['rewards_lpt']))} LPT`, withdraw `{_format_lpt(Decimal(out_json['totals']['withdraw_lpt']))} LPT`")
    lines.append("")

    lines.append("## By year")
    lines.append("")
    lines.append("| Year | Claim events | Rewards claimed (LPT) | Withdraw events | Stake withdrawn (LPT) | Withdraw / Rewards |")
    lines.append("|---:|---:|---:|---:|---:|---:|")
    for year in sorted(out_json["by_year"].keys()):
        row = out_json["by_year"][year]
        rewards = Decimal(str(row["rewards_lpt"]))
        withdraw = Decimal(str(row["withdraw_lpt"]))
        ratio = (withdraw / rewards) if rewards > 0 else Decimal(0)
        lines.append(
            f"| {year} | {int(row['claim_events']):,} | {_format_lpt(rewards)} | {int(row['withdraw_events']):,} | {_format_lpt(withdraw)} | {float(ratio)*100:.2f}% |"
        )
    lines.append("")

    lines.append("## By month")
    lines.append("")
    lines.append("| Month | Rewards claimed (LPT) | Stake withdrawn (LPT) | Withdraw / Rewards |")
    lines.append("|---:|---:|---:|---:|")
    for month in sorted(out_json["by_month"].keys()):
        row = out_json["by_month"][month]
        rewards = Decimal(str(row["rewards_lpt"]))
        withdraw = Decimal(str(row["withdraw_lpt"]))
        ratio = (withdraw / rewards) if rewards > 0 else Decimal(0)
        lines.append(f"| {month} | {_format_lpt(rewards)} | {_format_lpt(withdraw)} | {float(ratio)*100:.2f}% |")
    lines.append("")

    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

