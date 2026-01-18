from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import (
    OUTPUTS_DIR,
    abi_encode_int,
    coingecko_simple_price,
    decode_address_word,
    decode_int256,
    decode_uint256,
    eth_block_number,
    eth_call,
    env,
    find_block_by_timestamp,
    keccak_selector,
    rpc_call,
    write_json,
)

from Crypto.Hash import keccak


def keccak_topic(signature: str) -> str:
    h = keccak.new(digest_bits=256)
    h.update(signature.encode("utf-8"))
    return "0x" + h.hexdigest()


SWAP_TOPIC0 = keccak_topic("Swap(address,address,int256,int256,uint160,uint128,int24)")


def eth_get_logs(rpc_url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return rpc_call(rpc_url, "eth_getLogs", [params])


def parse_int256_word(word_hex: str) -> int:
    return decode_int256(word_hex)


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
            # Reduce range on common provider “too many results” / response-too-large cases.
            msg = str(e).lower()
            if any(k in msg for k in ["too many", "response size", "limit", "timeout", "more than", "range"]):
                step = max(100, step // 2)
                continue
            raise

        logs.extend(chunk)
        if max_logs is not None and len(logs) >= max_logs:
            return logs[:max_logs]

        # Adaptive step sizing: increase when chunks are small.
        if len(chunk) < 1000 and step < max_step:
            step = min(max_step, step * 2)

        cur = end + 1

    return logs


@dataclass(frozen=True)
class SwapAgg:
    swaps: int
    volume_usd: float
    fees_usd: float
    token0_in: float
    token1_in: float
    token0_fees: float
    token1_fees: float


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = int(p * (len(s) - 1))
    return s[idx]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute recent Uniswap v3 pool swap volume + fees from onchain logs.")
    parser.add_argument("--rpc-url", default=env("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc"))
    parser.add_argument("--pool", required=True, help="Uniswap v3 pool address.")
    parser.add_argument("--token0-coingecko-id", required=True)
    parser.add_argument("--token1-coingecko-id", required=True)
    parser.add_argument("--days", type=float, default=1.0, help="Lookback window (days).")
    parser.add_argument("--max-logs", type=int, default=None, help="Optional cap to avoid giant scans.")
    parser.add_argument("--out", default=str(OUTPUTS_DIR / "univ3-swap-analytics.json"))
    args = parser.parse_args()

    rpc_url = args.rpc_url
    pool = args.pool

    token0 = read_pool_token(rpc_url, pool, "token0()")
    token1 = read_pool_token(rpc_url, pool, "token1()")
    fee = read_pool_fee(rpc_url, pool)
    fee_frac = fee / 1_000_000

    dec0 = read_erc20_decimals(rpc_url, token0)
    dec1 = read_erc20_decimals(rpc_url, token1)

    prices = coingecko_simple_price([args.token0_coingecko_id, args.token1_coingecko_id], "usd")
    p0 = float(prices[args.token0_coingecko_id]["usd"])
    p1 = float(prices[args.token1_coingecko_id]["usd"])

    now_ts = int(time.time())
    start_ts = int(now_ts - args.days * 86400)

    latest = eth_block_number(rpc_url)
    start_block = find_block_by_timestamp(rpc_url, start_ts, high_block=latest)

    # Heuristic: Arbitrum-like chains have huge block counts; start with larger chunks.
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

    token0_in = 0.0
    token1_in = 0.0
    token0_fees = 0.0
    token1_fees = 0.0
    volume_usd = 0.0
    fees_usd = 0.0
    notionals: list[float] = []

    for log in logs:
        data = log["data"][2:]
        if len(data) < 64 * 5:
            continue
        words = [data[i : i + 64] for i in range(0, 64 * 5, 64)]
        amount0 = parse_int256_word(words[0])
        amount1 = parse_int256_word(words[1])

        if amount0 > 0:
            amt0 = amount0 / (10**dec0)
            token0_in += amt0
            token0_fees += amt0 * fee_frac
            usd = amt0 * p0
        elif amount1 > 0:
            amt1 = amount1 / (10**dec1)
            token1_in += amt1
            token1_fees += amt1 * fee_frac
            usd = amt1 * p1
        else:
            continue

        volume_usd += usd
        fees_usd += usd * fee_frac
        notionals.append(usd)

    agg = SwapAgg(
        swaps=len(logs),
        volume_usd=volume_usd,
        fees_usd=fees_usd,
        token0_in=token0_in,
        token1_in=token1_in,
        token0_fees=token0_fees,
        token1_fees=token1_fees,
    )

    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url,
        "pool": pool,
        "token0": token0,
        "token1": token1,
        "decimals": {"token0": dec0, "token1": dec1},
        "coingecko_ids": {"token0": args.token0_coingecko_id, "token1": args.token1_coingecko_id},
        "prices_usd": {"token0": p0, "token1": p1},
        "fee": fee,
        "fee_fraction": fee_frac,
        "window": {"days": args.days, "start_ts": start_ts, "end_ts": now_ts, "start_block": start_block, "end_block": latest},
        "aggregate": {
            "swaps": agg.swaps,
            "volume_usd": agg.volume_usd,
            "fees_usd": agg.fees_usd,
            "token0_in": agg.token0_in,
            "token1_in": agg.token1_in,
            "token0_fees": agg.token0_fees,
            "token1_fees": agg.token1_fees,
        },
        "notional_usd": {
            "count": len(notionals),
            "p50": percentile(notionals, 0.5),
            "p90": percentile(notionals, 0.9),
            "p99": percentile(notionals, 0.99),
            "max": max(notionals) if notionals else float("nan"),
            "min": min(notionals) if notionals else float("nan"),
        },
    }

    out_path = Path(args.out)
    write_json(out_path, out)
    print(f"Wrote `{out_path}` ({len(logs)} swap logs).")
    print(f"Volume: ${volume_usd:,.0f} | Fees: ${fees_usd:,.0f} | feeTier={fee/10_000:.2f}bps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
