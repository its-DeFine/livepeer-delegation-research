from __future__ import annotations

import argparse
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Crypto.Hash import keccak

from utils import (
    OUTPUTS_DIR,
    coingecko_simple_price,
    decode_address_word,
    decode_uint256,
    eth_block_number,
    eth_call,
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


def decode_indexed_address(topic_hex: str) -> str:
    if topic_hex.startswith("0x"):
        topic_hex = topic_hex[2:]
    return "0x" + topic_hex[-40:]


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute address-level Uniswap v3 swap analytics from onchain logs.")
    parser.add_argument("--rpc-url", default="https://arb1.arbitrum.io/rpc")
    parser.add_argument("--pool", required=True, help="Uniswap v3 pool address.")
    parser.add_argument("--token0-coingecko-id", required=True)
    parser.add_argument("--token1-coingecko-id", required=True)
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--max-logs", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--out", default=str(OUTPUTS_DIR / "univ3-swap-address-analytics.json"))
    args = parser.parse_args()

    rpc_url = args.rpc_url
    pool = args.pool

    token0 = decode_address_word(eth_call(rpc_url, pool, "0x" + keccak_selector("token0()"))[2:].rjust(64, "0"))
    token1 = decode_address_word(eth_call(rpc_url, pool, "0x" + keccak_selector("token1()"))[2:].rjust(64, "0"))
    dec0 = decode_uint256(eth_call(rpc_url, token0, "0x" + keccak_selector("decimals()")))
    dec1 = decode_uint256(eth_call(rpc_url, token1, "0x" + keccak_selector("decimals()")))

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

    sender_volume_usd: dict[str, float] = defaultdict(float)
    recipient_volume_usd: dict[str, float] = defaultdict(float)
    sender_counts: dict[str, int] = defaultdict(int)
    recipient_counts: dict[str, int] = defaultdict(int)

    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        sender = decode_indexed_address(topics[1]).lower()
        recipient = decode_indexed_address(topics[2]).lower()

        data = (log.get("data") or "0x")[2:]
        if len(data) < 64 * 2:
            continue
        amount0 = int(data[0:64], 16)
        amount1 = int(data[64:128], 16)
        # Interpret amounts as signed int256.
        if amount0 >= 2**255:
            amount0 -= 2**256
        if amount1 >= 2**255:
            amount1 -= 2**256

        # Notional approximation: use the token-in side for USD notional.
        if amount0 > 0:
            notional_usd = (amount0 / 10**dec0) * p0
        elif amount1 > 0:
            notional_usd = (amount1 / 10**dec1) * p1
        else:
            continue

        sender_volume_usd[sender] += notional_usd
        recipient_volume_usd[recipient] += notional_usd
        sender_counts[sender] += 1
        recipient_counts[recipient] += 1

    def top_items(d: dict[str, float], counts: dict[str, int]) -> list[dict[str, Any]]:
        items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)[: args.top_n]
        total = sum(d.values())
        out: list[dict[str, Any]] = []
        for addr, vol in items:
            out.append(
                {
                    "address": addr,
                    "volume_usd": vol,
                    "share": (vol / total) if total > 0 else 0.0,
                    "swaps": counts.get(addr, 0),
                }
            )
        return out

    total_vol = sum(sender_volume_usd.values())
    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url,
        "pool": pool,
        "token0": token0,
        "token1": token1,
        "decimals": {"token0": dec0, "token1": dec1},
        "window": {"days": args.days, "start_ts": start_ts, "end_ts": now_ts, "start_block": start_block, "end_block": latest},
        "prices_usd": {"token0": p0, "token1": p1},
        "counts": {
            "swap_logs": len(logs),
            "unique_senders": len(sender_volume_usd),
            "unique_recipients": len(recipient_volume_usd),
        },
        "aggregate": {"volume_usd": total_vol},
        "top": {
            "senders": top_items(sender_volume_usd, sender_counts),
            "recipients": top_items(recipient_volume_usd, recipient_counts),
        },
    }

    out_path = Path(args.out)
    write_json(out_path, out)
    print(f"Wrote `{out_path}` ({len(logs)} swap logs).")
    if total_vol > 0:
        top_sender_share = out["top"]["senders"][0]["share"] if out["top"]["senders"] else 0.0
        print(f"Total volume: ${total_vol:,.0f} | unique senders: {len(sender_volume_usd)} | top sender share: {top_sender_share:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
