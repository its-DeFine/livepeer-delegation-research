from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from pathlib import Path

from utils import (
    DATA_DIR,
    OUTPUTS_DIR,
    UniswapV3PoolState,
    abi_encode_address,
    abi_encode_uint,
    coingecko_simple_price,
    decode_uint256,
    eth_call,
    env,
    keccak_selector,
    read_univ3_pool_state,
    sqrt_price_from_tick,
)


DEFAULT_POOL = "0x4fD47e5102DFBF95541F64ED6FE13d4eD26D2546"  # LPT/WETH on Uniswap v3 (Arbitrum), 0.30% tier
DEFAULT_QUOTER = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"  # Uniswap V3 Quoter (v1)

LPT = "0x289ba1701C2F088cf0faf8B3705246331cB8A839"
WETH = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"


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


def compute_spot_weth_per_lpt(state: UniswapV3PoolState) -> Decimal:
    # For Uni v3 pools: price = (sqrtPriceX96 / 2^96)^2 in terms of token1/token0 (raw units).
    sqrt_price = Decimal(state.sqrt_price_x96) / Decimal(2**96)
    return sqrt_price * sqrt_price


def msb(value: int) -> int:
    return value.bit_length() - 1


def lsb(value: int) -> int:
    return (value & -value).bit_length() - 1


def nearest_initialized_ticks(*, rpc_url: str, pool: str, state: UniswapV3PoolState) -> tuple[int | None, int | None]:
    # Mirrors UniswapV3 TickBitmap.nextInitializedTickWithinOneWord logic, with a small word scan.
    tick = state.tick
    spacing = state.tick_spacing

    compressed = tick // spacing  # Python floors for negative ticks, matching desired behavior.
    tick_bitmap_sel = "0x" + keccak_selector("tickBitmap(int16)")

    cache: dict[int, int] = {}

    def get_word(word_pos: int) -> int:
        if word_pos in cache:
            return cache[word_pos]
        from utils import abi_encode_int

        data = tick_bitmap_sel + abi_encode_int(word_pos)
        res = eth_call(rpc_url, pool, data)
        val = int(res, 16)
        cache[word_pos] = val
        return val

    def next_initialized(comp: int, *, lte: bool) -> int | None:
        word = comp >> 8
        bit = comp % 256
        for _ in range(50):
            w = get_word(word)
            if lte:
                mask = (1 << (bit + 1)) - 1
                masked = w & mask
                if masked:
                    b = msb(masked)
                    return (word << 8) + b
                word -= 1
                bit = 255
            else:
                mask = ~((1 << (bit + 1)) - 1) & ((1 << 256) - 1)
                masked = w & mask
                if masked:
                    b = lsb(masked)
                    return (word << 8) + b
                word += 1
                bit = -1
        return None

    below = next_initialized(compressed, lte=True)
    above = next_initialized(compressed, lte=False)
    return (below * spacing if below is not None else None, above * spacing if above is not None else None)


def amount_to_next_tick_boundary(
    *,
    state: UniswapV3PoolState,
    spot_sqrt_price: Decimal,
    lower_tick: int | None,
    upper_tick: int | None,
) -> tuple[Decimal | None, Decimal | None]:
    # Approximate “how much token in” to push the price to the nearest initialized tick boundary,
    # within the current liquidity range, ignoring cross-range liquidity changes.
    L = Decimal(state.liquidity)
    fee_frac = Decimal(state.fee) / Decimal(1_000_000)

    amount0_in: Decimal | None = None
    amount1_in: Decimal | None = None

    if lower_tick is not None:
        sqrt_lower = sqrt_price_from_tick(lower_tick)
        if spot_sqrt_price > sqrt_lower:
            amount0 = L * (spot_sqrt_price - sqrt_lower) / (spot_sqrt_price * sqrt_lower)
            amount0_in = amount0 / (Decimal(1) - fee_frac)

    if upper_tick is not None:
        sqrt_upper = sqrt_price_from_tick(upper_tick)
        if sqrt_upper > spot_sqrt_price:
            amount1 = L * (sqrt_upper - spot_sqrt_price)
            amount1_in = amount1 / (Decimal(1) - fee_frac)

    return amount0_in, amount1_in


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute onchain price impact for LPT/WETH swaps on Uniswap v3 (Arbitrum).")
    parser.add_argument("--rpc-url", default=env("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc"))
    parser.add_argument("--pool", default=DEFAULT_POOL)
    parser.add_argument("--quoter", default=DEFAULT_QUOTER)
    parser.add_argument("--amounts-usd", default="1000,5000,10000,25000,50000")
    parser.add_argument("--out", default=str(OUTPUTS_DIR / "onchain-slippage.csv"))
    parser.add_argument("--include-tick-depth", action="store_true", help="Also estimate token amounts needed to hit the nearest initialized tick boundaries.")
    args = parser.parse_args()

    amounts = [int(x.strip()) for x in args.amounts_usd.split(",") if x.strip()]
    out_path = Path(args.out)

    prices = coingecko_simple_price(["livepeer", "ethereum"], "usd")
    lpt_usd = Decimal(str(prices["livepeer"]["usd"]))
    eth_usd = Decimal(str(prices["ethereum"]["usd"]))

    state = read_univ3_pool_state(args.rpc_url, args.pool)
    spot_weth_per_lpt = compute_spot_weth_per_lpt(state)
    spot_sqrt_price = Decimal(state.sqrt_price_x96) / Decimal(2**96)

    print(f"Pool: {args.pool} | fee={state.fee} | tick={state.tick}")
    print(f"Spot: {spot_weth_per_lpt:.10f} WETH/LPT | CoinGecko: LPT=${lpt_usd} ETH=${eth_usd}")
    print()

    rows: list[dict[str, str]] = []
    print("AmountUSD\tBuy impact\tSell impact\tBuy LPT out\tSell WETH out")
    for usd in amounts:
        usd_dec = Decimal(usd)

        weth_in = usd_dec / eth_usd
        amount_in_weth = int((weth_in * Decimal(10**18)).to_integral_value(rounding="ROUND_FLOOR"))
        lpt_out = quote_exact_input_single(
            rpc_url=args.rpc_url,
            quoter=args.quoter,
            token_in=WETH,
            token_out=LPT,
            fee=state.fee,
            amount_in=amount_in_weth,
        )
        lpt_out_dec = Decimal(lpt_out) / Decimal(10**18)
        exec_buy = (weth_in / lpt_out_dec) if lpt_out_dec != 0 else Decimal("NaN")
        buy_impact = (exec_buy / spot_weth_per_lpt - 1) * 100

        lpt_in = usd_dec / lpt_usd
        amount_in_lpt = int((lpt_in * Decimal(10**18)).to_integral_value(rounding="ROUND_FLOOR"))
        weth_out = quote_exact_input_single(
            rpc_url=args.rpc_url,
            quoter=args.quoter,
            token_in=LPT,
            token_out=WETH,
            fee=state.fee,
            amount_in=amount_in_lpt,
        )
        weth_out_dec = Decimal(weth_out) / Decimal(10**18)
        exec_sell = (weth_out_dec / lpt_in) if lpt_in != 0 else Decimal("NaN")
        sell_impact = (1 - exec_sell / spot_weth_per_lpt) * 100

        print(f"{usd:>8,}\t{buy_impact:>8.2f}%\t{sell_impact:>9.2f}%\t{lpt_out_dec:>10.4f}\t{weth_out_dec:>11.6f}")

        rows.append(
            {
                "amount_usd": str(usd),
                "buy_impact_pct": f"{buy_impact:.6f}",
                "sell_impact_pct": f"{sell_impact:.6f}",
                "buy_lpt_out": f"{lpt_out_dec:.18f}",
                "sell_weth_out": f"{weth_out_dec:.18f}",
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote `{out_path}`.")

    if args.include_tick_depth:
        lower_tick, upper_tick = nearest_initialized_ticks(rpc_url=args.rpc_url, pool=args.pool, state=state)
        amt0_in, amt1_in = amount_to_next_tick_boundary(
            state=state,
            spot_sqrt_price=spot_sqrt_price,
            lower_tick=lower_tick,
            upper_tick=upper_tick,
        )
        print("\nNearest initialized ticks:")
        print(f"- lower/equal: {lower_tick}")
        print(f"- upper:       {upper_tick}")
        print("\nApprox token-in to reach boundary (within current liquidity range):")
        if amt0_in is not None:
            print(f"- sell LPT in:  {amt0_in / Decimal(10**18):,.4f} LPT")
        else:
            print("- sell LPT in:  n/a")
        if amt1_in is not None:
            print(f"- buy  LPT with {amt1_in / Decimal(10**18):,.6f} WETH")
        else:
            print("- buy  LPT with n/a")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

