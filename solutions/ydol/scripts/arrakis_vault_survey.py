from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from utils import (
    DATA_DIR,
    OUTPUTS_DIR,
    abi_encode_uint,
    coingecko_simple_price,
    decode_address_word,
    decode_uint256,
    eth_call,
    env,
    keccak_selector,
    read_json,
    write_json,
)


ARRAKIS_META_VAULT_FACTORY = "0x820FB8127a689327C863de8433278d6181123982"
NATIVE_TOKEN_PLACEHOLDER = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

# Best-effort mapping for common assets to avoid hitting strict CoinGecko token_price limits.
KNOWN_ADDRESS_TO_COINGECKO_ID: dict[str, str] = {
    # Ethereum mainnet canonical addresses
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "ethereum",  # WETH
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "usd-coin",  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "tether",  # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f": "dai",  # DAI
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "wrapped-bitcoin",  # WBTC
}


def decode_address_array(hexdata: str) -> list[str]:
    if hexdata.startswith("0x"):
        hexdata = hexdata[2:]
    words = [hexdata[i : i + 64] for i in range(0, len(hexdata), 64)]
    if not words:
        return []
    offset = int(words[0], 16) // 32
    if offset >= len(words):
        return []
    length = int(words[offset], 16)
    out: list[str] = []
    for i in range(length):
        w = words[offset + 1 + i]
        out.append("0x" + w[-40:])
    return out


def read_addr(rpc_url: str, to: str, fn_sig: str) -> str:
    sel = "0x" + keccak_selector(fn_sig)
    res = eth_call(rpc_url, to, sel)
    return decode_address_word(res[2:].rjust(64, "0"))


def read_uint(rpc_url: str, to: str, fn_sig: str) -> int:
    sel = "0x" + keccak_selector(fn_sig)
    res = eth_call(rpc_url, to, sel)
    return decode_uint256(res)


def read_total_underlying(rpc_url: str, vault: str) -> tuple[int, int]:
    sel = "0x" + keccak_selector("totalUnderlying()")
    res = eth_call(rpc_url, vault, sel)
    data = res[2:].rjust(64 * 2, "0")
    return int(data[0:64], 16), int(data[64:128], 16)


def coingecko_token_price(
    *,
    platform_id: str,
    contract_address: str,
    vs_currency: str = "usd",
    cache_path: Path | None = None,
    refresh: bool = False,
) -> dict[str, dict[str, float]]:
    # CoinGecko token_price endpoint keyed by contract address.
    #
    # Note: CoinGecko free API currently limits token_price requests to 1 contract address.
    contract_address = contract_address.lower()
    cache_path = cache_path or (DATA_DIR / f"coingecko-token-price-{platform_id}-{vs_currency}.json")
    cache: dict[str, Any] = {}
    if cache_path.exists():
        cache = read_json(cache_path)
        if not isinstance(cache, dict):
            cache = {}
    if not refresh and contract_address in cache and isinstance(cache[contract_address], dict) and vs_currency in cache[contract_address]:
        return cache

    import requests

    url = f"https://api.coingecko.com/api/v3/simple/token_price/{platform_id}"
    max_attempts = 6
    backoff_s = 1.0
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(
                url,
                params={
                    "contract_addresses": contract_address,
                    "vs_currencies": vs_currency,
                },
                timeout=30,
                headers={"User-Agent": "proposal-review/1.0"},
            )
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"CoinGecko HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                cache.update(data)
                write_json(cache_path, cache)
            # Conservative throttling for free-tier limits.
            time.sleep(1.2)
            return cache
        except (requests.RequestException, ValueError) as e:
            last_err = e
            if attempt >= max_attempts:
                raise
            time.sleep(backoff_s)
            backoff_s = min(30.0, backoff_s * 2)

    raise RuntimeError("unreachable") from last_err


@dataclass(frozen=True)
class VaultRow:
    vault: str
    vault_type: str
    token0: str
    token1: str
    dec0: int
    dec1: int
    amount0: Decimal
    amount1: Decimal
    price0_usd: float | None
    price1_usd: float | None
    tvl_usd: float | None


def main() -> int:
    parser = argparse.ArgumentParser(description="Survey Arrakis Modular vaults from the onchain factory (TVL + tokens).")
    parser.add_argument("--rpc-url", default=env("ETHEREUM_RPC_URL", "https://ethereum.publicnode.com"))
    parser.add_argument("--platform-id", default="ethereum", help="CoinGecko platform id for token_price endpoint (e.g. ethereum, arbitrum-one).")
    parser.add_argument("--factory", default=ARRAKIS_META_VAULT_FACTORY)
    parser.add_argument("--type", choices=["public", "private", "both"], default="both")
    parser.add_argument("--max-vaults", type=int, default=100)
    parser.add_argument(
        "--fetch-token-prices",
        action="store_true",
        help="Fetch prices for unknown ERC20s via CoinGecko token_price (slow; may 429 on free tier).",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--out-json", default=str(OUTPUTS_DIR / "arrakis-vault-survey.json"))
    parser.add_argument("--out-csv", default=str(OUTPUTS_DIR / "arrakis-vault-survey.csv"))
    args = parser.parse_args()

    rpc_url = args.rpc_url
    factory = args.factory

    types = ["public", "private"] if args.type == "both" else [args.type]

    vaults: list[tuple[str, str]] = []
    for t in types:
        if t == "public":
            n = read_uint(rpc_url, factory, "numOfPublicVaults()")
            end = min(n, args.max_vaults)
            sel = "0x" + keccak_selector("publicVaults(uint256,uint256)")
        else:
            n = read_uint(rpc_url, factory, "numOfPrivateVaults()")
            end = min(n, args.max_vaults)
            sel = "0x" + keccak_selector("privateVaults(uint256,uint256)")

        res = eth_call(rpc_url, factory, sel + abi_encode_uint(0) + abi_encode_uint(end))
        addrs = decode_address_array(res)
        vaults.extend((a.lower(), t) for a in addrs)

    # De-dupe while preserving order.
    seen: set[str] = set()
    vaults_unique: list[tuple[str, str]] = []
    for a, t in vaults:
        if a in seen:
            continue
        seen.add(a)
        vaults_unique.append((a, t))

    # Gather token addresses only for vaults that currently hold something, to avoid huge token-price scans.
    vault_meta: dict[str, dict[str, Any]] = {}
    token_addrs: set[str] = set()
    for vault, vtype in vaults_unique:
        t0 = read_addr(rpc_url, vault, "token0()").lower()
        t1 = read_addr(rpc_url, vault, "token1()").lower()
        raw0, raw1 = read_total_underlying(rpc_url, vault)
        if raw0 == 0 and raw1 == 0:
            continue
        vault_meta[vault] = {"type": vtype, "token0": t0, "token1": t1, "raw0": raw0, "raw1": raw1}
        token_addrs.add(t0)
        token_addrs.add(t1)

    token_list = sorted(a for a in token_addrs if a not in {NATIVE_TOKEN_PLACEHOLDER, "0x0000000000000000000000000000000000000000"})
    prices: dict[str, dict[str, float]] = {}
    native_price_usd: float | None = None
    if NATIVE_TOKEN_PLACEHOLDER in token_addrs:
        native_price_usd = float(coingecko_simple_price(["ethereum"], "usd")["ethereum"]["usd"])

    # 1) Cheap path: map known addresses to IDs and batch via simple/price.
    known_ids = sorted({KNOWN_ADDRESS_TO_COINGECKO_ID[a] for a in token_list if a in KNOWN_ADDRESS_TO_COINGECKO_ID})
    if known_ids:
        id_prices = coingecko_simple_price(known_ids, "usd", cache_path=DATA_DIR / f"coingecko-simple-price-ids.json", refresh=args.refresh)
        for addr, cid in KNOWN_ADDRESS_TO_COINGECKO_ID.items():
            if cid in id_prices and addr in token_list:
                prices[addr] = {"usd": float(id_prices[cid]["usd"])}

    # 2) Slow path: attempt token_price for unknowns (often rate-limited on free tier).
    if args.fetch_token_prices:
        cache_path = DATA_DIR / f"coingecko-token-price-{args.platform_id}-usd.json"
        for token in token_list:
            if token in prices:
                continue
            try:
                prices.update(
                    coingecko_token_price(
                        platform_id=args.platform_id,
                        contract_address=token,
                        cache_path=cache_path,
                        refresh=args.refresh,
                    )
                )
            except Exception:
                # Leave price missing; continue.
                continue

    rows: list[VaultRow] = []
    for vault, meta in vault_meta.items():
        token0 = meta["token0"]
        token1 = meta["token1"]
        dec0 = 18 if token0 == NATIVE_TOKEN_PLACEHOLDER else read_uint(rpc_url, token0, "decimals()")
        dec1 = 18 if token1 == NATIVE_TOKEN_PLACEHOLDER else read_uint(rpc_url, token1, "decimals()")
        raw0 = int(meta["raw0"])
        raw1 = int(meta["raw1"])
        amt0 = Decimal(raw0) / Decimal(10**dec0)
        amt1 = Decimal(raw1) / Decimal(10**dec1)

        p0 = native_price_usd if token0 == NATIVE_TOKEN_PLACEHOLDER else prices.get(token0, {}).get("usd")
        p1 = native_price_usd if token1 == NATIVE_TOKEN_PLACEHOLDER else prices.get(token1, {}).get("usd")
        tvl = None
        if p0 is not None and p1 is not None:
            tvl = float(amt0) * float(p0) + float(amt1) * float(p1)

        rows.append(
            VaultRow(
                vault=vault,
                vault_type=meta["type"],
                token0=token0,
                token1=token1,
                dec0=dec0,
                dec1=dec1,
                amount0=amt0,
                amount1=amt1,
                price0_usd=p0,
                price1_usd=p1,
                tvl_usd=tvl,
            )
        )

    # Sort by TVL desc, with None last.
    rows_sorted = sorted(rows, key=lambda r: (-r.tvl_usd if r.tvl_usd is not None else float("inf")))

    out_json = Path(args.out_json)
    write_json(
        out_json,
        {
            "rpc_url": rpc_url,
            "platform_id": args.platform_id,
            "factory": factory,
            "counts": {"vaults": len(rows), "tokens": len(token_list)},
            "rows": [
                {
                    "vault": r.vault,
                    "type": r.vault_type,
                    "token0": r.token0,
                    "token1": r.token1,
                    "amount0": str(r.amount0),
                    "amount1": str(r.amount1),
                    "price0_usd": r.price0_usd,
                    "price1_usd": r.price1_usd,
                    "tvl_usd": r.tvl_usd,
                }
                for r in rows_sorted
            ],
        },
    )

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "vault",
                "type",
                "token0",
                "token1",
                "amount0",
                "amount1",
                "price0_usd",
                "price1_usd",
                "tvl_usd",
            ],
        )
        w.writeheader()
        for r in rows_sorted:
            w.writerow(
                {
                    "vault": r.vault,
                    "type": r.vault_type,
                    "token0": r.token0,
                    "token1": r.token1,
                    "amount0": str(r.amount0),
                    "amount1": str(r.amount1),
                    "price0_usd": "" if r.price0_usd is None else f"{r.price0_usd:.8f}",
                    "price1_usd": "" if r.price1_usd is None else f"{r.price1_usd:.8f}",
                    "tvl_usd": "" if r.tvl_usd is None else f"{r.tvl_usd:.2f}",
                }
            )

    print(f"Wrote `{out_json}` and `{out_csv}`.")
    if rows_sorted:
        top = rows_sorted[0]
        print(f"Top TVL (sample): {top.vault} | ${top.tvl_usd:,.0f}" if top.tvl_usd is not None else f"Top row: {top.vault} (no price)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
