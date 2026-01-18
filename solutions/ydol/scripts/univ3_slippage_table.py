from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from pathlib import Path

from utils import (
    OUTPUTS_DIR,
    UniswapV3PoolState,
    abi_encode_address,
    abi_encode_uint,
    coingecko_simple_price,
    decode_address_word,
    decode_uint256,
    eth_call,
    env,
    keccak_selector,
    read_univ3_pool_state,
    write_json,
)


DEFAULT_QUOTER = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"  # Uniswap V3 Quoter (v1)


def quote_exact_input_single(*, rpc_url: str, quoter: str, token_in: str, token_out: str, fee: int, amount_in: int) -> int:
    fn_sel = keccak_selector("quoteExactInputSingle(address,address,uint24,uint256,uint160)")
    data = (
        "0x"
        + fn_sel
        + abi_encode_address(token_in)
        + abi_encode_address(token_out)
        + abi_encode_uint(fee)
        + abi_encode_uint(amount_in)
        + abi_encode_uint(0)
    )
    res = eth_call(rpc_url, quoter, data)
    return decode_uint256(res)


def read_pool_token(rpc_url: str, pool: str, fn_sig: str) -> str:
    sel = "0x" + keccak_selector(fn_sig)
    res = eth_call(rpc_url, pool, sel)
    word = res[2:].rjust(64, "0")
    return decode_address_word(word)


def read_erc20_decimals(rpc_url: str, token: str) -> int:
    sel = "0x" + keccak_selector("decimals()")
    res = eth_call(rpc_url, token, sel)
    return decode_uint256(res)


def compute_spot_token1_per_token0(state: UniswapV3PoolState) -> Decimal:
    sqrt_price = Decimal(state.sqrt_price_x96) / Decimal(2**96)
    return sqrt_price * sqrt_price


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute onchain price impact table for a Uniswap v3 pool.")
    parser.add_argument("--rpc-url", default=env("RPC_URL", "https://arb1.arbitrum.io/rpc"))
    parser.add_argument("--pool", required=True, help="Uniswap v3 pool address.")
    parser.add_argument("--quoter", default=DEFAULT_QUOTER)
    parser.add_argument("--token0-coingecko-id", required=True)
    parser.add_argument("--token1-coingecko-id", required=True)
    parser.add_argument("--amounts-usd", default="1000,5000,10000,25000,50000")
    parser.add_argument("--out-csv", default=str(OUTPUTS_DIR / "univ3-slippage.csv"))
    parser.add_argument("--out-json", default=str(OUTPUTS_DIR / "univ3-slippage.json"))
    args = parser.parse_args()

    rpc_url = args.rpc_url
    pool = args.pool

    token0 = read_pool_token(rpc_url, pool, "token0()")
    token1 = read_pool_token(rpc_url, pool, "token1()")
    dec0 = read_erc20_decimals(rpc_url, token0)
    dec1 = read_erc20_decimals(rpc_url, token1)

    state = read_univ3_pool_state(rpc_url, pool)
    spot_t1_per_t0 = compute_spot_token1_per_token0(state)

    amounts = [int(x.strip()) for x in args.amounts_usd.split(",") if x.strip()]

    prices = coingecko_simple_price([args.token0_coingecko_id, args.token1_coingecko_id], "usd")
    t0_usd = Decimal(str(prices[args.token0_coingecko_id]["usd"]))
    t1_usd = Decimal(str(prices[args.token1_coingecko_id]["usd"]))

    rows: list[dict[str, str]] = []
    for usd in amounts:
        usd_dec = Decimal(usd)

        # Buy token0: spend token1 worth usd
        t1_in = usd_dec / t1_usd
        t1_in_wei = int((t1_in * Decimal(10**dec1)).to_integral_value(rounding="ROUND_FLOOR"))
        t0_out = Decimal(quote_exact_input_single(rpc_url=rpc_url, quoter=args.quoter, token_in=token1, token_out=token0, fee=state.fee, amount_in=t1_in_wei)) / Decimal(
            10**dec0
        )
        exec_buy = (t1_in / t0_out) if t0_out != 0 else Decimal("NaN")
        buy_impact = (exec_buy / spot_t1_per_t0 - 1) * 100

        # Sell token0: sell token0 worth usd
        t0_in = usd_dec / t0_usd
        t0_in_wei = int((t0_in * Decimal(10**dec0)).to_integral_value(rounding="ROUND_FLOOR"))
        t1_out = Decimal(quote_exact_input_single(rpc_url=rpc_url, quoter=args.quoter, token_in=token0, token_out=token1, fee=state.fee, amount_in=t0_in_wei)) / Decimal(
            10**dec1
        )
        exec_sell = (t1_out / t0_in) if t0_in != 0 else Decimal("NaN")
        sell_impact = (1 - exec_sell / spot_t1_per_t0) * 100

        rows.append(
            {
                "amount_usd": str(usd),
                "buy_token0_impact_pct": f"{buy_impact:.6f}",
                "sell_token0_impact_pct": f"{sell_impact:.6f}",
                "buy_token0_out": f"{t0_out:.18f}",
                "sell_token1_out": f"{t1_out:.18f}",
            }
        )

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    out = {
        "rpc_url": rpc_url,
        "pool": pool,
        "token0": token0,
        "token1": token1,
        "decimals": {"token0": dec0, "token1": dec1},
        "fee": state.fee,
        "spot_token1_per_token0": str(spot_t1_per_t0),
        "prices_usd": {"token0": str(t0_usd), "token1": str(t1_usd)},
        "rows": rows,
    }
    write_json(Path(args.out_json), out)
    print(f"Wrote `{out_csv}` and `{args.out_json}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
