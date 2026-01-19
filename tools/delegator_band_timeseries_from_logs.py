#!/usr/bin/env python3
"""
Livepeer Arbitrum — delegator bonded-stake distribution over time (event-scan, no archive required).

Why this exists:
- Arbitrum public RPC endpoints are typically **not archive**, so `eth_call` at old blocks can fail with
  `missing trie node` / `state is not available`.
- `eth_getLogs` works for historical ranges, so we derive per-delegator bonded stake by replaying
  BondingManager events in order.

What it computes:
- Snapshot distribution (active wallet count + bonded LPT) by bonded-stake band at month/quarter/year ends.
- Threshold cohorts (10k+, 100k+) over time.
- Net changes between snapshots.

Method:
1) Compute snapshot blocks by binary-searching block timestamps via `eth_getBlockByNumber` (not archive).
2) Scan BondingManager logs via `eth_getLogs` and replay these events:
   - Bond: sets bondedAmount to the emitted `bonded` value
   - Unbond: subtract `amount` from bondedAmount
   - Rebond: add `amount` back to bondedAmount
   (WithdrawStake does not affect bondedAmount)
3) At each snapshot block, bucket bondedAmount into stake bands and aggregate.

Stdlib-only; resumable via a pickle state file.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import pickle
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

ARBITRUM_PUBLIC_RPC = "https://arb1.arbitrum.io/rpc"
LIVEPEER_BONDING_MANAGER = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"

TOPIC0 = {
    # cast sig-event "Bond(address,address,address,uint256,uint256)"
    "Bond": "0xe5917769f276ddca9f2ee7c6b0b33e1d1e1b61008010ce622c632dd20d168a23",
    # cast sig-event "Unbond(address,address,uint256,uint256,uint256)"
    "Unbond": "0x2d5d98d189bee5496a08db2a5948cb7e5e786f09d17d0c3f228eb41776c24a06",
    # cast sig-event "Rebond(address,address,uint256,uint256)"
    "Rebond": "0x9f5b64cc71e1e26ff178caaa7877a04d8ce66fde989251870e80e6fbee690c17",
    # cast sig-event "EarningsClaimed(address,address,uint256,uint256,uint256,uint256)"
    "EarningsClaimed": "0xd7eab0765b772ea6ea859d5633baf737502198012e930f257f90013d9b211094",
    # optional: transfer of bond positions (ambiguous semantics; not applied to bondedAmount here)
    "TransferBond": "0xf136b986590e86cf1abd7b6600186a7a1178ad3cbbdf0f3312e79f6214a2a567",
}

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
            headers={"content-type": "application/json", "user-agent": "livepeer-research/delegator_band_timeseries_logs"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except HTTPError as e:
            retry_after_s: int | None = None
            try:
                ra = e.headers.get("Retry-After")
                if isinstance(ra, str):
                    ra = ra.strip()
                    if ra.isdigit():
                        retry_after_s = int(ra)
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
                    "missing trie node",
                    "state is not available",
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


_LAST_BLOCK_TS_RPC_AT_S: float = 0.0


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _topic_to_address(topic: str) -> str:
    if not topic.startswith("0x") or len(topic) != 66:
        raise ValueError(f"unexpected topic format: {topic}")
    return "0x" + topic[-40:]


def _decode_words(data_hex: str, n: int) -> List[int]:
    if not data_hex.startswith("0x"):
        raise ValueError("data must be 0x-prefixed")
    hex_str = data_hex[2:]
    need = 64 * n
    if len(hex_str) < need:
        raise ValueError(f"data too short: need {need} hex chars, got {len(hex_str)}")
    return [int(hex_str[i : i + 64], 16) for i in range(0, need, 64)]


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _block_timestamp(client: RpcClient, cache: Dict[int, int], block_number: int) -> int:
    if block_number in cache:
        return cache[block_number]
    # Throttle block timestamp lookups; monthly snapshot block discovery can otherwise trip 429s.
    global _LAST_BLOCK_TS_RPC_AT_S
    now = time.time()
    min_interval_s = 0.15
    if now - _LAST_BLOCK_TS_RPC_AT_S < min_interval_s:
        time.sleep(min_interval_s - (now - _LAST_BLOCK_TS_RPC_AT_S))
    block = _rpc_with_retries(client, "eth_getBlockByNumber", [hex(block_number), False])
    _LAST_BLOCK_TS_RPC_AT_S = time.time()
    if not isinstance(block, dict):
        raise RpcError(f"missing block {block_number}")
    ts = int(block["timestamp"], 16)
    cache[block_number] = ts
    return ts


def _find_block_at_or_before_ts(
    client: RpcClient,
    *,
    target_ts: int,
    low_block: int,
    high_block: int,
    ts_cache: Dict[int, int],
) -> int:
    low = int(low_block)
    high = int(high_block)
    if low > high:
        low, high = high, low

    low_ts = _block_timestamp(client, ts_cache, low)
    high_ts = _block_timestamp(client, ts_cache, high)
    if target_ts <= low_ts:
        return low
    if target_ts >= high_ts:
        return high

    while low < high:
        mid = (low + high + 1) // 2
        mid_ts = _block_timestamp(client, ts_cache, mid)
        if mid_ts <= target_ts:
            low = mid
        else:
            high = mid - 1
    return low


def _month_end_ts(year: int, month: int) -> int:
    last_day = calendar.monthrange(year, month)[1]
    dt = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return int(dt.timestamp())


def _build_snapshot_targets(start_ts: int, end_ts: int, interval: str) -> List[Tuple[str, int]]:
    start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)
    interval = interval.lower().strip()
    if interval not in ("monthly", "quarterly", "yearly"):
        raise ValueError("--interval must be one of: monthly, quarterly, yearly")

    targets: List[Tuple[str, int]] = []
    if interval == "monthly":
        y, m = start_dt.year, start_dt.month
        while True:
            ts = _month_end_ts(y, m)
            if ts >= start_ts and ts <= end_ts:
                targets.append((f"{y:04d}-{m:02d}-end", ts))
            if (y, m) >= (end_dt.year, end_dt.month):
                break
            m += 1
            if m > 12:
                y += 1
                m = 1
    elif interval == "quarterly":
        y, m = start_dt.year, start_dt.month
        while (y, m) <= (end_dt.year, end_dt.month):
            if m in (3, 6, 9, 12):
                ts = _month_end_ts(y, m)
                if ts >= start_ts and ts <= end_ts:
                    targets.append((f"{y:04d}-Q{((m-1)//3)+1}-end", ts))
            m += 1
            if m > 12:
                y += 1
                m = 1
    else:  # yearly
        for y in range(start_dt.year, end_dt.year + 1):
            ts = _month_end_ts(y, 12)
            if ts >= start_ts and ts <= end_ts:
                targets.append((f"{y:04d}-year-end", ts))

    if not targets or targets[-1][1] != end_ts:
        targets.append(("latest", end_ts))
    return targets


def _write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _write_text_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _markdown_table(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    out = []
    out.append("| " + " | ".join(header) + " |")
    out.append("| " + " | ".join(["---"] * len(header)) + " |")
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _md_escape(text: str) -> str:
    # Docusaurus parses Markdown as MDX; raw `<1` can be interpreted as JSX and break builds.
    return text.replace("<", "&lt;")


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _band_for_bonded_lpt(bonded_lpt: Decimal) -> Optional[str]:
    if bonded_lpt <= 0:
        return None
    if bonded_lpt < 1:
        return "<1 LPT"
    if bonded_lpt <= 10:
        return "1–10 LPT"
    if bonded_lpt <= 100:
        return "10–100 LPT"
    if bonded_lpt <= 1000:
        return "100–1k LPT"
    if bonded_lpt <= 10000:
        return "1k–10k LPT"
    return "10k+ LPT"


def _gini(values: List[Decimal]) -> float:
    if not values:
        return 0.0
    vals = [v for v in values if v > 0]
    if not vals:
        return 0.0
    vals.sort()
    n = len(vals)
    total = sum(vals)
    if total <= 0:
        return 0.0
    cum = Decimal(0)
    for i, v in enumerate(vals, start=1):
        cum += Decimal(i) * v
    g = (Decimal(2) * cum) / (Decimal(n) * total) - (Decimal(n + 1) / Decimal(n))
    # clamp due to float/rounding artifacts
    return float(max(Decimal(0), min(Decimal(1), g)))


def _hhi(values: List[Decimal]) -> float:
    if not values:
        return 0.0
    vals = [v for v in values if v > 0]
    if not vals:
        return 0.0
    total = sum(vals)
    if total <= 0:
        return 0.0
    h = Decimal(0)
    for v in vals:
        s = v / total
        h += s * s
    return float(h)


def _effective_n(hhi: float) -> float:
    return (1.0 / hhi) if hhi > 0 else 0.0


def _top_shares(values_desc: List[Decimal], top_ns: List[int]) -> Dict[str, float]:
    vals = [v for v in values_desc if v > 0]
    if not vals:
        return {str(n): 0.0 for n in top_ns}
    total = sum(vals)
    if total <= 0:
        return {str(n): 0.0 for n in top_ns}
    out: Dict[str, float] = {}
    for n in top_ns:
        k = max(0, min(int(n), len(vals)))
        out[str(n)] = float(sum(vals[:k]) / total)
    return out


def _nakamoto(values_desc: List[Decimal], threshold_share: Decimal) -> int:
    vals = [v for v in values_desc if v > 0]
    if not vals:
        return 0
    total = sum(vals)
    if total <= 0:
        return 0
    cum = Decimal(0)
    for i, v in enumerate(vals, start=1):
        cum += v
        if (cum / total) >= threshold_share:
            return i
    return len(vals)


def _get_logs_range(
    client: RpcClient,
    *,
    address: str,
    topic0_any_of: List[str],
    from_block: int,
    to_block: int,
    max_splits: int = 24,
) -> List[dict]:
    params = {
        "address": address,
        "topics": [topic0_any_of],
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
    }
    try:
        res = _rpc_with_retries(client, "eth_getLogs", [params])
        return res or []
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


@dataclass
class ScanState:
    version: int
    rpc_url: str
    bonding_manager: str
    from_block: int
    to_block: int
    chunk_size: int
    next_block: int
    interval: str
    snapshot_targets: List[Tuple[str, int]]  # (label, target_ts)
    snapshot_blocks: List[Dict[str, Any]]  # computed blocks meta + computed distribution
    next_snapshot_idx: int
    bonded_wei_by_address: Dict[str, int]
    delegate_by_delegator: Dict[str, str]
    updated_at_utc: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", default=ARBITRUM_PUBLIC_RPC)
    parser.add_argument("--bonding-manager", default=LIVEPEER_BONDING_MANAGER)
    parser.add_argument("--addresses-json", default="data/arbitrum_delegator_addresses.json")
    parser.add_argument("--from-block", type=int, default=5856381)
    parser.add_argument("--to-block", type=int, default=0, help="0 = latest (minus --block-lag)")
    parser.add_argument("--block-lag", type=int, default=200)
    parser.add_argument("--chunk-size", type=int, default=200_000)
    parser.add_argument("--interval", default="monthly", help="monthly|quarterly|yearly")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--state-pkl", default="artifacts/timeseries_scan_state.pkl")
    parser.add_argument("--out-md", default="research/delegator-band-timeseries.md")
    parser.add_argument("--out-json", default="research/delegator-band-timeseries.json")
    args = parser.parse_args()

    with open(args.addresses_json, "r", encoding="utf-8") as f:
        payload = json.load(f)
    addresses = payload["addresses"] if isinstance(payload, dict) else payload
    if not isinstance(addresses, list) or not addresses:
        raise SystemExit(f"addresses json missing 'addresses' list: {args.addresses_json}")
    addresses = [_normalize_address(a) for a in addresses]

    client = RpcClient(str(args.rpc_url))

    ts_cache: Dict[int, int] = {}
    latest_block = int(_rpc_with_retries(client, "eth_blockNumber", []) or "0x0", 16)
    latest_snapshot_block = max(0, latest_block - max(0, int(args.block_lag)))

    to_block = int(args.to_block)
    if to_block <= 0:
        to_block = latest_snapshot_block
    else:
        to_block = min(to_block, latest_snapshot_block)
    from_block = max(0, int(args.from_block))
    if from_block >= to_block:
        raise SystemExit(f"from_block {from_block} >= to_block {to_block}")

    # Resume support
    state: Optional[ScanState] = None
    if args.resume and os.path.exists(args.state_pkl):
        with open(args.state_pkl, "rb") as f:
            raw = pickle.load(f)
        if isinstance(raw, ScanState):
            state = raw

    if state is None:
        start_ts = _block_timestamp(client, ts_cache, from_block)
        end_ts = _block_timestamp(client, ts_cache, to_block)
        targets = _build_snapshot_targets(start_ts, end_ts, str(args.interval))

        snapshot_blocks: List[Dict[str, Any]] = []
        print(f"computing snapshot blocks: {len(targets)} targets ({args.interval})")
        for label, ts in targets:
            b = _find_block_at_or_before_ts(client, target_ts=int(ts), low_block=from_block, high_block=to_block, ts_cache=ts_cache)
            b_ts = _block_timestamp(client, ts_cache, b)
            if label == "latest" or label.endswith("-end") or label.endswith("year-end"):
                print(f"  snapshot {label}: ts={ts} -> block={b} ({_iso(int(b_ts))})")
            snapshot_blocks.append(
                {
                    "label": label,
                    "target_ts": int(ts),
                    "target_iso": _iso(int(ts)),
                    "snapshot_block": int(b),
                    "snapshot_ts": int(b_ts),
                    "snapshot_iso": _iso(int(b_ts)),
                    "distribution": None,
                }
            )

        bonded = {a: 0 for a in addresses}
        delegate_by_delegator = {a: "" for a in addresses}
        state = ScanState(
            version=2,
            rpc_url=str(args.rpc_url),
            bonding_manager=_normalize_address(args.bonding_manager),
            from_block=from_block,
            to_block=to_block,
            chunk_size=int(args.chunk_size),
            next_block=from_block,
            interval=str(args.interval),
            snapshot_targets=targets,
            snapshot_blocks=snapshot_blocks,
            next_snapshot_idx=0,
            bonded_wei_by_address=bonded,
            delegate_by_delegator=delegate_by_delegator,
            updated_at_utc=datetime.now(tz=timezone.utc).isoformat(),
        )
        os.makedirs(os.path.dirname(args.state_pkl), exist_ok=True)
        with open(args.state_pkl, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)

    # Migrate/ensure fields on resumed state.
    if not isinstance(getattr(state, "delegate_by_delegator", None), dict):
        state.delegate_by_delegator = {a: "" for a in addresses}
    if int(getattr(state, "version", 0) or 0) < 2:
        state.version = 2

    # Validate resume settings are consistent enough
    if state.bonding_manager != _normalize_address(args.bonding_manager):
        raise SystemExit("state-pkl bonding_manager mismatch; delete state or pass matching --bonding-manager")

    # Helper: compute distribution at current bonded state
    band_labels = ["<1 LPT", "1–10 LPT", "10–100 LPT", "100–1k LPT", "1k–10k LPT", "10k+ LPT"]

    def compute_distribution() -> Dict[str, Any]:
        total_bonded = Decimal(0)
        active = 0
        by_band_counts = {l: 0 for l in band_labels}
        by_band_bonded = {l: Decimal(0) for l in band_labels}
        thr10_count = 0
        thr10_bonded = Decimal(0)
        thr100_count = 0
        thr100_bonded = Decimal(0)

        delegator_stakes: List[Tuple[str, Decimal]] = []
        delegate_stakes: Dict[str, Decimal] = {}
        unknown_delegate_wallets = 0
        unknown_delegate_bonded = Decimal(0)

        for a in addresses:
            amt = int(state.bonded_wei_by_address.get(a, 0))
            if amt <= 0:
                continue
            bonded_lpt = _wei_to_lpt(amt)
            if bonded_lpt <= 0:
                continue
            active += 1
            total_bonded += bonded_lpt
            delegator_stakes.append((a, bonded_lpt))

            delegate_raw = str(state.delegate_by_delegator.get(a, "") or "").lower()
            if delegate_raw.startswith("0x") and len(delegate_raw) == 42 and delegate_raw != "0x0000000000000000000000000000000000000000":
                delegate = delegate_raw
            else:
                delegate = "unknown"
                unknown_delegate_wallets += 1
                unknown_delegate_bonded += bonded_lpt
            delegate_stakes[delegate] = delegate_stakes.get(delegate, Decimal(0)) + bonded_lpt

            band = _band_for_bonded_lpt(bonded_lpt)
            if band is None:
                continue
            by_band_counts[band] += 1
            by_band_bonded[band] += bonded_lpt
            if bonded_lpt >= 10000:
                thr10_count += 1
                thr10_bonded += bonded_lpt
            if bonded_lpt >= 100000:
                thr100_count += 1
                thr100_bonded += bonded_lpt

        delegator_values = [s for _a, s in delegator_stakes]
        delegator_values_desc = sorted(delegator_values, reverse=True)
        top_ns = [1, 5, 10, 20, 50, 100]

        delegator_hhi = _hhi(delegator_values)
        delegator_gini = _gini(delegator_values)
        delegator_top_share = _top_shares(delegator_values_desc, top_ns)

        top_delegators: List[Dict[str, Any]] = []
        for addr, stake in sorted(delegator_stakes, key=lambda kv: kv[1], reverse=True)[:20]:
            top_delegators.append(
                {
                    "address": addr,
                    "bonded_lpt": str(stake),
                    "share_of_bonded_lpt": float(stake / total_bonded) if total_bonded > 0 else 0.0,
                }
            )

        delegate_stakes_known = {k: v for k, v in delegate_stakes.items() if k != "unknown"}
        delegate_values = list(delegate_stakes_known.values())
        delegate_values_desc = sorted(delegate_values, reverse=True)

        delegate_hhi = _hhi(delegate_values)
        delegate_gini = _gini(delegate_values)
        delegate_top_share = _top_shares(delegate_values_desc, top_ns)
        nakamoto_33 = _nakamoto(delegate_values_desc, Decimal("0.33"))
        nakamoto_50 = _nakamoto(delegate_values_desc, Decimal("0.50"))

        delegates_ge_10k = sum(1 for v in delegate_values if v >= Decimal("10000"))
        delegates_ge_100k = sum(1 for v in delegate_values if v >= Decimal("100000"))
        delegates_ge_1m = sum(1 for v in delegate_values if v >= Decimal("1000000"))

        top_delegates: List[Dict[str, Any]] = []
        for delegate, stake in sorted(delegate_stakes_known.items(), key=lambda kv: kv[1], reverse=True)[:25]:
            top_delegates.append(
                {
                    "delegate": delegate,
                    "bonded_lpt": str(stake),
                    "share_of_bonded_lpt": float(stake / total_bonded) if total_bonded > 0 else 0.0,
                }
            )

        bands_out: Dict[str, Any] = {}
        for b in band_labels:
            c = by_band_counts[b]
            s = by_band_bonded[b]
            bands_out[b] = {
                "active_delegators": c,
                "bonded_lpt": str(s),
                "share_of_active_count": (float(c) / float(active)) if active > 0 else 0.0,
                "share_of_bonded_lpt": float(s / total_bonded) if total_bonded > 0 else 0.0,
            }

        return {
            "active_delegators": active,
            "total_bonded_lpt": str(total_bonded),
            "bands": bands_out,
            "thresholds": {
                ">=10k_lpt": {"active_delegators": thr10_count, "bonded_lpt": str(thr10_bonded)},
                ">=100k_lpt": {"active_delegators": thr100_count, "bonded_lpt": str(thr100_bonded)},
            },
            "concentration": {
                "delegators": {
                    "gini": delegator_gini,
                    "hhi": delegator_hhi,
                    "effective_n": _effective_n(delegator_hhi),
                    "top_share": delegator_top_share,
                    "top_delegators": top_delegators,
                },
                "delegates": {
                    "active_delegates": len(delegate_stakes_known),
                    "unknown_delegate_wallets": unknown_delegate_wallets,
                    "unknown_delegate_bonded_lpt": str(unknown_delegate_bonded),
                    "gini": delegate_gini,
                    "hhi": delegate_hhi,
                    "effective_n": _effective_n(delegate_hhi),
                    "top_share": delegate_top_share,
                    "nakamoto": {"33%": nakamoto_33, "50%": nakamoto_50},
                    "delegates_ge_10k": delegates_ge_10k,
                    "delegates_ge_100k": delegates_ge_100k,
                    "delegates_ge_1m": delegates_ge_1m,
                    "top_delegates": top_delegates,
                },
            },
        }

    def save_state() -> None:
        state.updated_at_utc = datetime.now(tz=timezone.utc).isoformat()
        tmp = args.state_pkl + ".tmp"
        os.makedirs(os.path.dirname(args.state_pkl), exist_ok=True)
        with open(tmp, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, args.state_pkl)

    # Advance snapshots for ranges with no logs (or after finishing a chunk)
    def emit_snapshots_up_to_block(block_number: int) -> None:
        while state.next_snapshot_idx < len(state.snapshot_blocks):
            snap = state.snapshot_blocks[state.next_snapshot_idx]
            if int(snap["snapshot_block"]) > int(block_number):
                return
            if snap.get("distribution") is None:
                snap["distribution"] = compute_distribution()
            state.next_snapshot_idx += 1

    topic0_any = [
        TOPIC0["Bond"],
        TOPIC0["Unbond"],
        TOPIC0["Rebond"],
        TOPIC0["EarningsClaimed"],
        TOPIC0["TransferBond"],
    ]

    # Main scan loop
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

        # Process logs in order. eth_getLogs is ordered by (blockNumber, logIndex).
        for log in logs:
            block_number = int(log.get("blockNumber", "0x0"), 16)
            if block_number <= 0:
                continue

            emit_snapshots_up_to_block(block_number - 1)

            topics = log.get("topics") or []
            if not topics:
                continue
            topic0 = str(topics[0]).lower()
            data_hex = str(log.get("data") or "0x")

            if topic0 == TOPIC0["Bond"]:
                if len(topics) < 4:
                    continue
                new_delegate = _topic_to_address(topics[1]).lower()
                delegator = _topic_to_address(topics[3]).lower()
                if delegator not in state.bonded_wei_by_address:
                    continue
                additional, bonded = _decode_words(data_hex, 2)
                # `bonded` is the post-bond total bondedAmount for this delegator.
                state.bonded_wei_by_address[delegator] = int(bonded)
                state.delegate_by_delegator[delegator] = new_delegate

            elif topic0 == TOPIC0["Unbond"]:
                if len(topics) < 3:
                    continue
                delegator = _topic_to_address(topics[2]).lower()
                if delegator not in state.bonded_wei_by_address:
                    continue
                _lock_id, amount, _withdraw_round = _decode_words(data_hex, 3)
                cur = int(state.bonded_wei_by_address.get(delegator, 0))
                state.bonded_wei_by_address[delegator] = max(0, cur - int(amount))

            elif topic0 == TOPIC0["Rebond"]:
                if len(topics) < 3:
                    continue
                delegator = _topic_to_address(topics[2]).lower()
                if delegator not in state.bonded_wei_by_address:
                    continue
                _lock_id, amount = _decode_words(data_hex, 2)
                cur = int(state.bonded_wei_by_address.get(delegator, 0))
                state.bonded_wei_by_address[delegator] = max(0, cur + int(amount))

            elif topic0 == TOPIC0["EarningsClaimed"]:
                # Rewards are auto-bonded when claimed (compound into bondedAmount).
                if len(topics) < 3:
                    continue
                delegator = _topic_to_address(topics[2]).lower()
                if delegator not in state.bonded_wei_by_address:
                    continue
                rewards, _fees, _start_round, _end_round = _decode_words(data_hex, 4)
                cur = int(state.bonded_wei_by_address.get(delegator, 0))
                state.bonded_wei_by_address[delegator] = max(0, cur + int(rewards))

            elif topic0 == TOPIC0["TransferBond"]:
                # Ambiguous semantics (could be unbonding lock transfer). We do not apply it to bondedAmount.
                # Still, it can affect "who holds stake" if it transfers bonded positions. If we find that it
                # materially affects totals vs `eth_call` at latest, we can implement full semantics later.
                continue

        # At the end of the chunk, we have fully processed up to chunk_to.
        emit_snapshots_up_to_block(chunk_to)

        state.next_block = chunk_to + 1
        save_state()

        if chunk_from == state.from_block or (chunk_to // state.chunk_size) % 25 == 0 or chunk_to == state.to_block:
            print(f"scanned {chunk_from:,}..{chunk_to:,} ({len(logs):,} logs); next_snapshot_idx={state.next_snapshot_idx}/{len(state.snapshot_blocks)}")

    # Finalize all remaining snapshots (in case to_block is past last log block)
    emit_snapshots_up_to_block(state.to_block)
    save_state()

    # Compose output
    snapshots_out: List[Dict[str, Any]] = []
    for snap in state.snapshot_blocks:
        dist = snap.get("distribution") or {}
        snapshots_out.append(
            {
                "label": snap["label"],
                "target_ts": snap["target_ts"],
                "target_iso": snap["target_iso"],
                "snapshot_block": snap["snapshot_block"],
                "snapshot_ts": snap["snapshot_ts"],
                "snapshot_iso": snap["snapshot_iso"],
                **dist,
            }
        )

    deltas: List[Dict[str, Any]] = []
    for i in range(1, len(snapshots_out)):
        prev = snapshots_out[i - 1]
        cur = snapshots_out[i]
        delta: Dict[str, Any] = {
            "from": prev["label"],
            "to": cur["label"],
            "active_delegators": int(cur["active_delegators"]) - int(prev["active_delegators"]),
            "total_bonded_lpt": str(Decimal(cur["total_bonded_lpt"]) - Decimal(prev["total_bonded_lpt"])),
            "bands": {},
            "thresholds": {},
        }
        for b in band_labels:
            delta["bands"][b] = {
                "active_delegators": int(cur["bands"][b]["active_delegators"]) - int(prev["bands"][b]["active_delegators"]),
                "bonded_lpt": str(Decimal(cur["bands"][b]["bonded_lpt"]) - Decimal(prev["bands"][b]["bonded_lpt"])),
            }
        for k in (">=10k_lpt", ">=100k_lpt"):
            delta["thresholds"][k] = {
                "active_delegators": int(cur["thresholds"][k]["active_delegators"]) - int(prev["thresholds"][k]["active_delegators"]),
                "bonded_lpt": str(Decimal(cur["thresholds"][k]["bonded_lpt"]) - Decimal(prev["thresholds"][k]["bonded_lpt"])),
            }
        deltas.append(delta)

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "rpc_url": str(args.rpc_url),
            "bonding_manager": state.bonding_manager,
            "from_block": state.from_block,
            "to_block": state.to_block,
            "block_lag": int(args.block_lag),
            "addresses_json": str(args.addresses_json),
            "addresses_total": len(addresses),
            "interval": state.interval,
            "topic0": TOPIC0,
            "state_pkl": str(args.state_pkl),
            "state_updated_at_utc": state.updated_at_utc,
        },
        "definition": {
            "active_delegator": "bondedAmount > 0 derived from event replay at snapshot block",
            "bands": [
                {"label": "<1 LPT", "low_inclusive_lpt": "0", "high_inclusive_lpt": "1"},
                {"label": "1–10 LPT", "low_inclusive_lpt": "1", "high_inclusive_lpt": "10"},
                {"label": "10–100 LPT", "low_inclusive_lpt": "10", "high_inclusive_lpt": "100"},
                {"label": "100–1k LPT", "low_inclusive_lpt": "100", "high_inclusive_lpt": "1000"},
                {"label": "1k–10k LPT", "low_inclusive_lpt": "1000", "high_inclusive_lpt": "10000"},
                {"label": "10k+ LPT", "low_inclusive_lpt": "10000", "high_inclusive_lpt": None},
            ],
        },
        "snapshots": snapshots_out,
        "deltas": deltas,
    }

    _write_json_atomic(args.out_json, out_json)

    # Markdown report
    lines: List[str] = []
    lines.append("# Livepeer Arbitrum — Delegator stake bands over time (event replay)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- RPC: `{args.rpc_url}` (BondingManager `{state.bonding_manager}`)")
    lines.append(f"- Range: `{state.from_block}` → `{state.to_block}` (block_lag `{int(args.block_lag)}`)")
    lines.append(f"- Interval: `{state.interval}`")
    lines.append(f"- Universe: `{len(addresses):,}` addresses (`{args.addresses_json}`)")
    lines.append("- Delegate mapping: last observed `Bond(newDelegate, oldDelegate, delegator, ...)` per wallet (event replay)")
    lines.append("")

    lines.append("## Active delegator counts (by bonded stake band)")
    lines.append("")
    band_labels_md = [_md_escape(b) for b in band_labels]
    count_rows: List[List[str]] = [["Snapshot"] + band_labels_md + ["Active total"]]
    for s in snapshots_out:
        row = [s["label"]]
        for b in band_labels:
            row.append(f"{int(s['bands'][b]['active_delegators']):,}")
        row.append(f"{int(s['active_delegators']):,}")
        count_rows.append(row)
    lines.append(_markdown_table(count_rows))
    lines.append("")

    lines.append("## Bonded LPT (by bonded stake band)")
    lines.append("")
    stake_rows: List[List[str]] = [["Snapshot"] + band_labels_md + ["Bonded total"]]
    for s in snapshots_out:
        row = [s["label"]]
        for b in band_labels:
            row.append(_format_lpt(Decimal(s["bands"][b]["bonded_lpt"])))
        row.append(_format_lpt(Decimal(s["total_bonded_lpt"])))
        stake_rows.append(row)
    lines.append(_markdown_table(stake_rows))
    lines.append("")

    lines.append("## 10k+ and 100k+ cohorts")
    lines.append("")
    thr_rows: List[List[str]] = [["Snapshot", "10k+ wallets", "10k+ bonded LPT", "100k+ wallets", "100k+ bonded LPT"]]
    for s in snapshots_out:
        thr10 = s["thresholds"][">=10k_lpt"]
        thr100 = s["thresholds"][">=100k_lpt"]
        thr_rows.append(
            [
                s["label"],
                f"{int(thr10['active_delegators']):,}",
                _format_lpt(Decimal(thr10["bonded_lpt"])),
                f"{int(thr100['active_delegators']):,}",
                _format_lpt(Decimal(thr100["bonded_lpt"])),
            ]
        )
    lines.append(_markdown_table(thr_rows))
    lines.append("")

    def _fmt_pct(x: float) -> str:
        return f"{x*100:.2f}%"

    def _fmt_float(x: float, *, places: int = 4) -> str:
        return f"{x:.{places}f}"

    lines.append("## Stake concentration — delegators (wallets)")
    lines.append("")
    dconc_rows: List[List[str]] = [
        ["Snapshot", "Active wallets", "Top10 share", "Top20 share", "Gini", "HHI", "Eff N"],
    ]
    for s in snapshots_out:
        c = (s.get("concentration") or {}).get("delegators") or {}
        top_share = c.get("top_share") or {}
        dconc_rows.append(
            [
                s["label"],
                f"{int(s['active_delegators']):,}",
                _fmt_pct(float(top_share.get("10") or 0.0)),
                _fmt_pct(float(top_share.get("20") or 0.0)),
                _fmt_float(float(c.get("gini") or 0.0)),
                _fmt_float(float(c.get("hhi") or 0.0)),
                _fmt_float(float(c.get("effective_n") or 0.0), places=2),
            ]
        )
    lines.append(_markdown_table(dconc_rows))
    lines.append("")

    lines.append("## Stake concentration — delegates (orchestrators / delegate addresses)")
    lines.append("")
    oconc_rows: List[List[str]] = [
        ["Snapshot", "Active delegates", "Nakamoto 33%", "Nakamoto 50%", "Top10 share", "HHI", "Eff N", "≥100k delegates", "≥1m delegates"],
    ]
    for s in snapshots_out:
        c = (s.get("concentration") or {}).get("delegates") or {}
        top_share = c.get("top_share") or {}
        nak = c.get("nakamoto") or {}
        oconc_rows.append(
            [
                s["label"],
                f"{int(c.get('active_delegates') or 0):,}",
                str(int(nak.get("33%") or 0)),
                str(int(nak.get("50%") or 0)),
                _fmt_pct(float(top_share.get("10") or 0.0)),
                _fmt_float(float(c.get("hhi") or 0.0)),
                _fmt_float(float(c.get("effective_n") or 0.0), places=2),
                str(int(c.get("delegates_ge_100k") or 0)),
                str(int(c.get("delegates_ge_1m") or 0)),
            ]
        )
    lines.append(_markdown_table(oconc_rows))
    lines.append("")

    latest = snapshots_out[-1] if snapshots_out else None
    if latest:
        d = (latest.get("concentration") or {}).get("delegates") or {}
        top_delegates = d.get("top_delegates") or []
        if isinstance(top_delegates, list) and top_delegates:
            lines.append("## Top delegates (latest snapshot)")
            lines.append("")
            trows: List[List[str]] = [["Rank", "Delegate", "Bonded LPT", "Share of bonded"]]
            for i, row in enumerate(top_delegates[:15], start=1):
                trows.append(
                    [
                        str(i),
                        str(row.get("delegate") or ""),
                        _format_lpt(Decimal(str(row.get("bonded_lpt") or "0"))),
                        _fmt_pct(float(row.get("share_of_bonded_lpt") or 0.0)),
                    ]
                )
            lines.append(_markdown_table(trows))
            lines.append("")

    lines.append("## Net changes between snapshots")
    lines.append("")
    delta_rows: List[List[str]] = [["From → To", "Δ active delegators", "Δ bonded LPT", "Δ 10k+ wallets", "Δ 10k+ bonded LPT"]]
    for d in deltas:
        delta_rows.append(
            [
                f"{d['from']} → {d['to']}",
                f"{int(d['active_delegators']):,}",
                _format_lpt(Decimal(d["total_bonded_lpt"])),
                f"{int(d['thresholds']['>=10k_lpt']['active_delegators']):,}",
                _format_lpt(Decimal(d["thresholds"][">=10k_lpt"]["bonded_lpt"])),
            ]
        )
    lines.append(_markdown_table(delta_rows))
    lines.append("")

    _write_text_atomic(args.out_md, "\n".join(lines) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
