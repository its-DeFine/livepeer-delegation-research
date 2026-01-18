from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Crypto.Hash import keccak

from utils import (
    OUTPUTS_DIR,
    coingecko_simple_price,
    decode_address_word,
    decode_int256,
    decode_uint256,
    eth_block_number,
    eth_get_block_timestamp,
    eth_call,
    env,
    find_block_by_timestamp,
    keccak_selector,
    rpc_call,
    write_json,
)


def keccak_topic(signature: str) -> str:
    h = keccak.new(digest_bits=256)
    h.update(signature.encode("utf-8"))
    return "0x" + h.hexdigest()


SWAP_TOPIC0 = keccak_topic("Swap(address,address,int256,int256,uint160,uint128,int24)")


def eth_get_logs(rpc_url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return rpc_call(rpc_url, "eth_getLogs", [params])


def read_pool_token(rpc_url: str, pool: str, fn_sig: str) -> str:
    sel = "0x" + keccak_selector(fn_sig)
    res = eth_call(rpc_url, pool, sel)
    word = res[2:].rjust(64, "0")
    return decode_address_word(word)


def read_pool_fee(rpc_url: str, pool: str) -> int:
    sel = "0x" + keccak_selector("fee()")
    res = eth_call(rpc_url, pool, sel)
    return decode_uint256(res)


def read_erc20_decimals(rpc_url: str, token: str) -> int:
    sel = "0x" + keccak_selector("decimals()")
    res = eth_call(rpc_url, token, sel)
    return decode_uint256(res)


def fetch_logs_chunked(
    *,
    rpc_url: str,
    address: str,
    topic0: str,
    from_block: int,
    to_block: int,
    initial_step: int,
    max_step: int,
    max_logs: int | None,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    step = initial_step
    cur = from_block

    while cur <= to_block:
        end = min(cur + step - 1, to_block)
        params = {"fromBlock": hex(cur), "toBlock": hex(end), "address": address, "topics": [topic0]}
        try:
            chunk = eth_get_logs(rpc_url, params)
        except RuntimeError as e:
            msg = str(e).lower()
            if any(k in msg for k in ["too many", "response size", "limit", "timeout", "more than", "range"]):
                step = max(100, step // 2)
                continue
            raise

        logs.extend(chunk)
        if max_logs is not None and len(logs) >= max_logs:
            return logs[:max_logs]

        if len(chunk) < 1000 and step < max_step:
            step = min(max_step, step * 2)

        cur = end + 1

    return logs


@dataclass(frozen=True)
class SwapPoint:
    ts: int
    block_number: int
    tick: int
    notional_usd: float
    direction: str  # "buy" or "sell" relative to token0 (token0 in => sell token0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Empirically estimate how quickly Uniswap v3 pool price (tick) reverts after mid-sized swaps."
    )
    parser.add_argument("--rpc-url", default=env("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc"))
    parser.add_argument("--pool", required=True)
    parser.add_argument("--token0-coingecko-id", required=True)
    parser.add_argument("--token1-coingecko-id", required=True)
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--min-usd", type=float, default=500.0)
    parser.add_argument("--max-usd", type=float, default=2000.0)
    parser.add_argument(
        "--window-seconds",
        type=int,
        default=None,
        help="Look ahead this many seconds for a reversion (requires block timestamp lookups; slower).",
    )
    parser.add_argument(
        "--window-swaps",
        type=int,
        default=5,
        help="Look ahead this many subsequent swaps for a reversion (fast; recommended for low-volume pools).",
    )
    parser.add_argument(
        "--revert-ticks",
        type=int,
        default=60,
        help="Consider reverted once tick returns within this many ticks of the pre-swap tick.",
    )
    parser.add_argument(
        "--include-time",
        action="store_true",
        help="Also compute reversion latency in seconds (adds block timestamp lookups; modestly slower).",
    )
    parser.add_argument("--max-logs", type=int, default=None)
    parser.add_argument("--out", default=str(OUTPUTS_DIR / "univ3-reversion.json"))
    args = parser.parse_args()

    rpc_url = args.rpc_url
    pool = args.pool

    token0 = read_pool_token(rpc_url, pool, "token0()")
    token1 = read_pool_token(rpc_url, pool, "token1()")
    fee = read_pool_fee(rpc_url, pool)

    dec0 = read_erc20_decimals(rpc_url, token0)
    dec1 = read_erc20_decimals(rpc_url, token1)

    prices = coingecko_simple_price([args.token0_coingecko_id, args.token1_coingecko_id], "usd")
    p0 = float(prices[args.token0_coingecko_id]["usd"])
    p1 = float(prices[args.token1_coingecko_id]["usd"])

    now_ts = int(time.time())
    start_ts = int(now_ts - args.days * 86400)

    latest = eth_block_number(rpc_url)
    start_block = find_block_by_timestamp(rpc_url, start_ts, high_block=latest)

    initial_step = 50_000 if "arb" in rpc_url else 10_000
    max_step = 200_000 if "arb" in rpc_url else 30_000

    logs = fetch_logs_chunked(
        rpc_url=rpc_url,
        address=pool,
        topic0=SWAP_TOPIC0,
        from_block=start_block,
        to_block=latest,
        initial_step=initial_step,
        max_step=max_step,
        max_logs=args.max_logs,
    )

    points: list[SwapPoint] = []
    for log in logs:
        data = log["data"][2:]
        if len(data) < 64 * 5:
            continue
        words = [data[i : i + 64] for i in range(0, 64 * 5, 64)]
        amount0 = decode_int256(words[0])
        amount1 = decode_int256(words[1])
        tick = decode_int256(words[4])
        # Timestamp is optional; avoid expensive block lookups unless requested.
        ts = 0
        bn = int(log["blockNumber"], 16)

        if amount0 > 0:
            amt0 = amount0 / (10**dec0)
            usd = amt0 * p0
            direction = "sell_token0"
        elif amount1 > 0:
            amt1 = amount1 / (10**dec1)
            usd = amt1 * p1
            direction = "buy_token0"
        else:
            continue

        points.append(SwapPoint(ts=ts, block_number=bn, tick=tick, notional_usd=usd, direction=direction))

    need_block_ts = args.window_seconds is not None or args.include_time
    block_ts_cache: dict[int, int] = {}

    def get_ts(block_number: int) -> int:
        if block_number in block_ts_cache:
            return block_ts_cache[block_number]
        ts2 = eth_get_block_timestamp(rpc_url, block_number)
        block_ts_cache[block_number] = ts2
        return ts2

    if args.window_seconds is not None:
        # Fill timestamps for points (needed for time-window scan).
        for idx, pt in enumerate(points):
            points[idx] = SwapPoint(
                ts=get_ts(pt.block_number),
                block_number=pt.block_number,
                tick=pt.tick,
                notional_usd=pt.notional_usd,
                direction=pt.direction,
            )

    candidates: list[int] = []
    for i in range(1, len(points)):
        usd = points[i].notional_usd
        if args.min_usd <= usd <= args.max_usd:
            candidates.append(i)

    reverted = 0
    times_to_revert: list[int] = []
    times_to_revert_seconds: list[int] = []
    for idx in candidates:
        pre_tick = points[idx - 1].tick
        if args.window_seconds is not None:
            t0 = points[idx].ts
            j = idx + 1
            while j < len(points) and points[j].ts - t0 <= args.window_seconds:
                if abs(points[j].tick - pre_tick) <= args.revert_ticks:
                    reverted += 1
                    times_to_revert.append(points[j].ts - t0)
                    break
                j += 1
        else:
            # Fast path: check next N swaps.
            end = min(len(points) - 1, idx + args.window_swaps)
            for j in range(idx + 1, end + 1):
                if abs(points[j].tick - pre_tick) <= args.revert_ticks:
                    reverted += 1
                    times_to_revert.append(j - idx)  # swaps-to-revert
                    if need_block_ts:
                        t0 = get_ts(points[idx].block_number)
                        t1 = get_ts(points[j].block_number)
                        times_to_revert_seconds.append(t1 - t0)
                    break

    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url,
        "pool": pool,
        "token0": token0,
        "token1": token1,
        "coingecko_ids": {"token0": args.token0_coingecko_id, "token1": args.token1_coingecko_id},
        "fee": fee,
        "window": {"days": args.days, "start_ts": start_ts, "end_ts": now_ts, "start_block": start_block, "end_block": latest},
        "params": {
            "min_usd": args.min_usd,
            "max_usd": args.max_usd,
            "window_seconds": args.window_seconds,
            "window_swaps": args.window_swaps,
            "revert_ticks": args.revert_ticks,
        },
        "counts": {
            "swap_logs": len(logs),
            "decoded_swaps": len(points),
            "candidates": len(candidates),
            "reverted": reverted,
            "revert_rate": (reverted / len(candidates)) if candidates else 0.0,
            "median_revert_value": (sorted(times_to_revert)[len(times_to_revert) // 2] if times_to_revert else None),
            "median_revert_unit": ("seconds" if args.window_seconds is not None else "swaps"),
            "median_revert_seconds": (
                sorted(times_to_revert_seconds)[len(times_to_revert_seconds) // 2] if times_to_revert_seconds else None
            ),
        },
        "revert_times": times_to_revert[:5000],  # cap to keep JSON sane
        "revert_times_seconds": times_to_revert_seconds[:5000],
    }

    out_path = Path(args.out)
    write_json(out_path, out)
    print(f"Wrote `{out_path}`.")
    print(f"Candidates: {len(candidates)} | Reverted: {reverted} | Rate: {out['counts']['revert_rate']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
