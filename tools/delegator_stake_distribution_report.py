#!/usr/bin/env python3
"""
Livepeer delegator stake distribution (Arbitrum One).

Computes how many active delegators fall into stake bands (e.g. 1–10 LPT),
and how much total LPT those bands represent. Generates simple SVG pie charts.

Stdlib-only; uses JSON-RPC batch requests to avoid rate limiting.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ARBITRUM_PUBLIC_RPC = "https://arb1.arbitrum.io/rpc"
LIVEPEER_BONDING_MANAGER = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"

# getDelegator(address)(uint256,uint256,address,uint256,uint256,uint256,uint256)
# cast sig "getDelegator(address)" => 0xa64ad595
GET_DELEGATOR_SELECTOR = "a64ad595"

LPT_DECIMALS = 18


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

    def call_raw(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "livepeer-research/delegator_stake_distribution"},
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
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise RpcError(f"invalid JSON-RPC response: {raw[:200]!r}") from e


def _rpc_with_retries(fn, *, max_tries: int = 10, max_backoff_s: float = 120.0) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return fn()
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

            sleep_s = min(2 ** (attempt - 1), max_backoff_s)
            retry_after_s = getattr(e, "retry_after_s", None)
            if isinstance(retry_after_s, int) and retry_after_s > 0:
                sleep_s = max(sleep_s, float(retry_after_s))
            sleep_s = sleep_s * (1 + random.uniform(-0.15, 0.15))
            time.sleep(max(0.5, sleep_s))


def _write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _to_lpt(amount_wei: int) -> float:
    return amount_wei / float(10**LPT_DECIMALS)


def _call_data_get_delegator(addr: str) -> str:
    a = addr.lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return "0x" + GET_DELEGATOR_SELECTOR + ("0" * 24) + a[2:]


def _chunked(seq: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _batch_get_delegator_bonded_amounts(
    rpc: RpcClient,
    *,
    addresses: List[str],
    bonding_manager: str,
    block_tag: str,
    batch_size: int,
    target_calls_per_second: Optional[float],
    cache_path: Optional[str],
    cache_meta: Optional[Dict[str, Any]],
    existing_bonded: Optional[Dict[str, int]],
) -> Dict[str, int]:
    bonded: Dict[str, int] = dict(existing_bonded or {})
    next_id = 1
    pending = [a for a in addresses if a.lower() not in bonded]
    total = len(pending)
    total_batches = (total + batch_size - 1) // batch_size
    processed = 0

    for batch_idx, batch in enumerate(_chunked(pending, batch_size), start=1):
        t0 = time.time()
        payload = []
        id_to_addr: Dict[int, str] = {}
        for addr in batch:
            call_obj = {"to": bonding_manager, "data": _call_data_get_delegator(addr)}
            payload.append({"jsonrpc": "2.0", "id": next_id, "method": "eth_call", "params": [call_obj, block_tag]})
            id_to_addr[next_id] = addr
            next_id += 1

        def fetch_and_parse() -> Dict[str, int]:
            resp = rpc.call_raw(payload)
            if not isinstance(resp, list):
                raise RpcError(f"unexpected batch response type: {type(resp)}")

            batch_bonded: Dict[str, int] = {}
            for item in resp:
                if not isinstance(item, dict) or "id" not in item:
                    continue
                req_id = item.get("id")
                addr = id_to_addr.get(req_id)
                if addr is None:
                    continue
                if item.get("error"):
                    raise RpcError(f"eth_call error for {addr}: {item['error']}")
                out = item.get("result")
                if not isinstance(out, str) or not out.startswith("0x") or len(out) < 2 + 64:
                    raise RpcError(f"unexpected eth_call output for {addr}: {out!r}")
                bonded_amount = int(out[2 : 2 + 64], 16)
                batch_bonded[addr.lower()] = bonded_amount

            if len(batch_bonded) != len(batch):
                raise RpcError(f"incomplete batch response: got {len(batch_bonded)}/{len(batch)} results")
            return batch_bonded

        batch_bonded = _rpc_with_retries(fetch_and_parse)
        bonded.update(batch_bonded)

        processed += len(batch_bonded)
        elapsed_s = max(time.time() - t0, 1e-6)
        if target_calls_per_second and target_calls_per_second > 0:
            target_elapsed_s = len(batch) / float(target_calls_per_second)
            if elapsed_s < target_elapsed_s:
                time.sleep(target_elapsed_s - elapsed_s)

        if cache_path and cache_meta is not None:
            cache_payload = dict(cache_meta)
            cache_payload["bonded_amount_wei_by_address"] = {k: str(v) for k, v in bonded.items()}
            _write_json_atomic(cache_path, cache_payload)

        print(f"[{batch_idx}/{total_batches}] fetched {processed}/{total} delegators", flush=True)

    return bonded


@dataclass(frozen=True)
class Band:
    label: str
    low_inclusive: float
    high_inclusive: Optional[float]  # None => infinity

    def contains(self, x: float) -> bool:
        if x < self.low_inclusive:
            return False
        if self.high_inclusive is None:
            return True
        return x <= self.high_inclusive


def _format_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def _svg_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _write_pie_svg(
    *,
    path: str,
    title: str,
    slices: List[Tuple[str, float, str]],  # (label, value, color)
    value_fmt,
    width: int = 880,
    height: int = 520,
) -> None:
    total = sum(v for _label, v, _color in slices if v > 0)
    cx, cy = 260, height // 2
    r = 180

    def polar(angle_rad: float) -> Tuple[float, float]:
        return (cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad))

    # Start at top (-90deg)
    angle = -math.pi / 2

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    parts.append('<rect width="100%" height="100%" fill="white"/>')
    parts.append(f'<text x="24" y="40" font-family="Inter, system-ui, -apple-system, Segoe UI, Roboto" font-size="22" font-weight="700">{_svg_escape(title)}</text>')

    if total <= 0:
        parts.append('<text x="24" y="80" font-family="Inter, system-ui, -apple-system, Segoe UI, Roboto" font-size="14">No data</text>')
        parts.append("</svg>")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts) + "\n")
        return

    legend_x = 520
    legend_y = 90
    legend_line_h = 26

    for i, (label, value, color) in enumerate(slices):
        if value <= 0:
            continue
        frac = value / total
        sweep = frac * 2 * math.pi
        start = angle
        end = angle + sweep
        x1, y1 = polar(start)
        x2, y2 = polar(end)
        large = 1 if sweep > math.pi else 0
        # draw wedge
        d = f"M {cx} {cy} L {x1:.3f} {y1:.3f} A {r} {r} 0 {large} 1 {x2:.3f} {y2:.3f} Z"
        parts.append(f'<path d="{d}" fill="{color}" stroke="white" stroke-width="2"/>')
        angle = end

        # legend item
        y = legend_y + i * legend_line_h
        parts.append(f'<rect x="{legend_x}" y="{y-14}" width="14" height="14" fill="{color}"/>')
        parts.append(
            f'<text x="{legend_x+20}" y="{y-2}" font-family="Inter, system-ui, -apple-system, Segoe UI, Roboto" font-size="13">'
            f'{_svg_escape(label)} — {value_fmt(value)} ({_format_pct(frac)})'
            "</text>"
        )

    # Outline circle
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="1"/>')
    parts.append("</svg>")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--addresses-json", default="data/arbitrum_delegator_addresses.json")
    parser.add_argument("--rpc-url", default=ARBITRUM_PUBLIC_RPC)
    parser.add_argument("--bonding-manager", default=LIVEPEER_BONDING_MANAGER)
    parser.add_argument("--block-lag", type=int, default=200)
    parser.add_argument("--snapshot-block", type=int, default=None)
    parser.add_argument("--out-dir", default="docs/img")
    parser.add_argument("--report-md", default="research/delegator-stake-distribution.md")
    parser.add_argument("--report-json", default="research/delegator-stake-distribution.json")
    parser.add_argument("--cache-json", default="artifacts/delegator-bonded-amounts-cache.json")
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument("--target-calls-per-second", type=float, default=10.0)
    args = parser.parse_args()

    with open(args.addresses_json, "r", encoding="utf-8") as f:
        payload = json.load(f)
    addresses = payload["addresses"] if isinstance(payload, dict) else payload
    if not isinstance(addresses, list) or not addresses:
        raise SystemExit("addresses json missing 'addresses' list")
    addresses = [str(a).lower() for a in addresses]
    address_set = set(addresses)

    cached_payload: Optional[Dict[str, Any]] = None
    if args.cache_json and os.path.exists(args.cache_json):
        try:
            with open(args.cache_json, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                cached_payload = raw
        except Exception:
            cached_payload = None

    rpc = RpcClient(args.rpc_url)
    block_hex = _rpc_with_retries(lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}))
    if not isinstance(block_hex, dict) or not isinstance(block_hex.get("result"), str):
        raise RpcError(f"unexpected eth_blockNumber response: {block_hex!r}")
    latest_block_number = int(block_hex["result"], 16)

    snapshot_block_number: int
    if args.snapshot_block is not None:
        snapshot_block_number = max(0, int(args.snapshot_block))
    else:
        cached_snapshot_block = None
        if (
            cached_payload
            and cached_payload.get("snapshot_block") is not None
            and str(cached_payload.get("bonding_manager", "")).lower() == str(args.bonding_manager).lower()
        ):
            try:
                cached_snapshot_block = int(cached_payload["snapshot_block"])
            except Exception:
                cached_snapshot_block = None
        if cached_snapshot_block is not None:
            snapshot_block_number = max(0, cached_snapshot_block)
        else:
            snapshot_block_number = max(0, latest_block_number - max(0, int(args.block_lag)))
    block_tag = hex(snapshot_block_number)

    ts_hex = _rpc_with_retries(
        lambda: rpc.call_raw(
            {"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber", "params": [block_tag, False]}
        )
    )
    if not isinstance(ts_hex, dict) or not isinstance(ts_hex.get("result"), dict):
        raise RpcError(f"unexpected eth_getBlockByNumber response: {ts_hex!r}")
    block_ts = int(ts_hex["result"]["timestamp"], 16)

    existing_bonded: Dict[str, int] = {}
    if (
        cached_payload
        and cached_payload.get("snapshot_block") == snapshot_block_number
        and str(cached_payload.get("bonding_manager", "")).lower() == str(args.bonding_manager).lower()
    ):
        m = cached_payload.get("bonded_amount_wei_by_address")
        if isinstance(m, dict):
            for k, v in m.items():
                if not isinstance(k, str) or k.lower() not in address_set:
                    continue
                existing_bonded[k.lower()] = int(v)

    cache_meta = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "latest_block_at_start": latest_block_number,
        "snapshot_block": snapshot_block_number,
        "snapshot_block_timestamp": block_ts,
        "block_lag": int(args.block_lag),
        "rpc_url": args.rpc_url,
        "bonding_manager": str(args.bonding_manager).lower(),
        "addresses_json": args.addresses_json,
        "addresses_total": len(addresses),
    }

    bonded_by_addr = _batch_get_delegator_bonded_amounts(
        rpc,
        addresses=addresses,
        bonding_manager=args.bonding_manager,
        block_tag=block_tag,
        batch_size=max(1, args.batch_size),
        target_calls_per_second=args.target_calls_per_second,
        cache_path=args.cache_json,
        cache_meta=cache_meta,
        existing_bonded=existing_bonded,
    )

    bonded_by_addr = {a: bonded_by_addr.get(a, 0) for a in addresses}
    active = {a: v for a, v in bonded_by_addr.items() if v > 0}
    active_lpt = {a: _to_lpt(v) for a, v in active.items()}

    total_active = len(active_lpt)
    total_all = len(addresses)
    total_bonded_lpt = sum(active_lpt.values())

    bands = [
        Band("<1 LPT", 0.0, 1.0),
        Band("1–10 LPT", 1.0, 10.0),
        Band("10–100 LPT", 10.0, 100.0),
        Band("100–1k LPT", 100.0, 1000.0),
        Band("1k–10k LPT", 1000.0, 10000.0),
        Band("10k+ LPT", 10000.0, None),
    ]

    # Assign to bands (note: boundaries are inclusive; e.g., 10 goes into 1–10, 100 into 10–100).
    band_counts: Dict[str, int] = {b.label: 0 for b in bands}
    band_stake: Dict[str, float] = {b.label: 0.0 for b in bands}

    def band_for(x: float) -> str:
        if 0 < x < 1:
            return "<1 LPT"
        if 1 <= x <= 10:
            return "1–10 LPT"
        if 10 < x <= 100:
            return "10–100 LPT"
        if 100 < x <= 1000:
            return "100–1k LPT"
        if 1000 < x <= 10000:
            return "1k–10k LPT"
        return "10k+ LPT"

    for _addr, lpt in active_lpt.items():
        label = band_for(lpt)
        band_counts[label] += 1
        band_stake[label] += lpt

    small_label = "1–10 LPT"
    small_count = band_counts[small_label]
    small_stake = band_stake[small_label]

    out = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "rpc_url": args.rpc_url,
            "bonding_manager": args.bonding_manager,
            "addresses_json": args.addresses_json,
            "batch_size": args.batch_size,
            "target_calls_per_second": args.target_calls_per_second,
            "latest_block_at_start": latest_block_number,
            "snapshot_block": snapshot_block_number,
            "snapshot_block_timestamp": block_ts,
            "block_lag": int(args.block_lag),
        },
        "totals": {
            "delegators_in_addresses_list": total_all,
            "delegators_active_now": total_active,
            "delegators_inactive_now": total_all - total_active,
            "total_active_bonded_lpt": total_bonded_lpt,
        },
        "bands": {
            label: {
                "active_delegators": band_counts[label],
                "bonded_lpt": band_stake[label],
                "share_of_active_delegators": (band_counts[label] / total_active) if total_active else 0,
                "share_of_active_bonded_lpt": (band_stake[label] / total_bonded_lpt) if total_bonded_lpt else 0,
            }
            for label in band_counts
        },
        "small_1_10_lpt": {
            "active_delegators": small_count,
            "bonded_lpt": small_stake,
            "share_of_active_delegators": (small_count / total_active) if total_active else 0,
            "share_of_active_bonded_lpt": (small_stake / total_bonded_lpt) if total_bonded_lpt else 0,
        },
    }

    os.makedirs(os.path.dirname(args.report_json), exist_ok=True)
    with open(args.report_json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")

    palette = ["#2563eb", "#16a34a", "#f59e0b", "#ef4444", "#a855f7", "#0ea5e9"]
    slices_counts = [(b.label, float(band_counts[b.label]), palette[i % len(palette)]) for i, b in enumerate(bands)]
    slices_stake = [(b.label, float(band_stake[b.label]), palette[i % len(palette)]) for i, b in enumerate(bands)]

    _write_pie_svg(
        path=os.path.join(args.out_dir, "delegators_active_count_pie.svg"),
        title=f"Active Delegators — Count by Stake Band (block {snapshot_block_number})",
        slices=slices_counts,
        value_fmt=lambda v: f"{int(v):,}",
    )
    _write_pie_svg(
        path=os.path.join(args.out_dir, "delegators_active_stake_pie.svg"),
        title=f"Active Delegators — Bonded LPT by Stake Band (block {snapshot_block_number})",
        slices=slices_stake,
        value_fmt=lambda v: f"{v:,.0f} LPT",
    )

    os.makedirs(os.path.dirname(args.report_md), exist_ok=True)
    with open(args.report_md, "w", encoding="utf-8") as f:
        f.write("# Livepeer Delegators — Stake Distribution (Arbitrum)\n\n")
        f.write(f"- Latest block at start: `{latest_block_number}`\n")
        f.write(f"- Snapshot block: `{snapshot_block_number}` (lag `{int(args.block_lag)}`) — {_iso(block_ts)}\n")
        f.write(f"- Address universe: `{total_all}` delegators (ever bonded; extracted from on-chain logs)\n")
        f.write(f"- Active now (bondedAmount > 0): `{total_active}`\n")
        f.write(f"- Total bonded (active): `{total_bonded_lpt:,.3f} LPT`\n\n")

        f.write("## 1–10 LPT Delegators (\"small\")\n\n")
        f.write(f"- Count: `{small_count:,}` / `{total_active:,}` active delegators ({_format_pct(out['small_1_10_lpt']['share_of_active_delegators'])})\n")
        f.write(f"- Bonded stake: `{small_stake:,.3f} LPT` / `{total_bonded_lpt:,.3f} LPT` ({_format_pct(out['small_1_10_lpt']['share_of_active_bonded_lpt'])})\n\n")

        f.write("## Bands (active only)\n\n")
        f.write("| Band | Active delegators | % of active | Bonded LPT | % of bonded |\n")
        f.write("|---|---:|---:|---:|---:|\n")
        for b in bands:
            row = out["bands"][b.label]
            f.write(
                f"| {b.label} | {row['active_delegators']:,} | {_format_pct(row['share_of_active_delegators'])} | {row['bonded_lpt']:,.3f} | {_format_pct(row['share_of_active_bonded_lpt'])} |\n"
            )
        f.write("\n## Charts\n\n")
        f.write("- Count: `docs/img/delegators_active_count_pie.svg`\n")
        f.write("- Bonded stake: `docs/img/delegators_active_stake_pie.svg`\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
