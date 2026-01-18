from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class TradeResult:
    total_usd: float
    direction: str
    input_amount: str
    output_amount: str
    exec_price_token1_per_token0: str
    impact_pct: str


def _impact_pct(*, direction: str, exec_price: Decimal, spot: Decimal) -> Decimal:
    # Positive means worse execution than spot.
    if direction == "buy_token0":
        return (exec_price / spot - 1) * 100
    if direction == "sell_token0":
        return (1 - exec_price / spot) * 100
    raise ValueError(f"unknown direction: {direction}")


def simulate_trade(
    *,
    rpc_url: str,
    quoter: str,
    token0: str,
    token1: str,
    dec0: int,
    dec1: int,
    fee: int,
    spot_t1_per_t0: Decimal,
    t0_usd: Decimal,
    t1_usd: Decimal,
    total_usd: Decimal,
    direction: str,
) -> TradeResult:
    if direction == "buy_token0":
        t1_in = total_usd / t1_usd
        t1_in_wei = int((t1_in * Decimal(10**dec1)).to_integral_value(rounding="ROUND_FLOOR"))
        t0_out = Decimal(
            quote_exact_input_single(rpc_url=rpc_url, quoter=quoter, token_in=token1, token_out=token0, fee=fee, amount_in=t1_in_wei)
        ) / Decimal(10**dec0)
        exec_price = (t1_in / t0_out) if t0_out != 0 else Decimal("NaN")
        impact = _impact_pct(direction=direction, exec_price=exec_price, spot=spot_t1_per_t0)
        return TradeResult(
            total_usd=float(total_usd),
            direction=direction,
            input_amount=str(t1_in),
            output_amount=str(t0_out),
            exec_price_token1_per_token0=str(exec_price),
            impact_pct=str(impact),
        )

    if direction == "sell_token0":
        t0_in = total_usd / t0_usd
        t0_in_wei = int((t0_in * Decimal(10**dec0)).to_integral_value(rounding="ROUND_FLOOR"))
        t1_out = Decimal(
            quote_exact_input_single(rpc_url=rpc_url, quoter=quoter, token_in=token0, token_out=token1, fee=fee, amount_in=t0_in_wei)
        ) / Decimal(10**dec1)
        exec_price = (t1_out / t0_in) if t0_in != 0 else Decimal("NaN")
        impact = _impact_pct(direction=direction, exec_price=exec_price, spot=spot_t1_per_t0)
        return TradeResult(
            total_usd=float(total_usd),
            direction=direction,
            input_amount=str(t0_in),
            output_amount=str(t1_out),
            exec_price_token1_per_token0=str(exec_price),
            impact_pct=str(impact),
        )

    raise ValueError(f"unknown direction: {direction}")


def simulate_chunked_reverted(
    *,
    rpc_url: str,
    quoter: str,
    token0: str,
    token1: str,
    dec0: int,
    dec1: int,
    fee: int,
    spot_t1_per_t0: Decimal,
    t0_usd: Decimal,
    t1_usd: Decimal,
    total_usd: Decimal,
    chunk_usd: Decimal,
    direction: str,
) -> TradeResult:
    # "Best case" chunking: assume each chunk executes against the same spot state (i.e., price fully reverts between chunks).
    remaining = total_usd
    input_total = Decimal(0)
    output_total = Decimal(0)

    while remaining > 0:
        cur_usd = chunk_usd if remaining >= chunk_usd else remaining
        res = simulate_trade(
            rpc_url=rpc_url,
            quoter=quoter,
            token0=token0,
            token1=token1,
            dec0=dec0,
            dec1=dec1,
            fee=fee,
            spot_t1_per_t0=spot_t1_per_t0,
            t0_usd=t0_usd,
            t1_usd=t1_usd,
            total_usd=cur_usd,
            direction=direction,
        )

        input_total += Decimal(res.input_amount)
        output_total += Decimal(res.output_amount)
        remaining -= cur_usd

    exec_price = (input_total / output_total) if direction == "buy_token0" else (output_total / input_total)
    impact = _impact_pct(direction=direction, exec_price=exec_price, spot=spot_t1_per_t0)
    return TradeResult(
        total_usd=float(total_usd),
        direction=direction,
        input_amount=str(input_total),
        output_amount=str(output_total),
        exec_price_token1_per_token0=str(exec_price),
        impact_pct=str(impact),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare single-swap vs chunked-with-reversion execution (best-case) for a Uniswap v3 pool."
    )
    parser.add_argument("--rpc-url", default=env("RPC_URL", "https://arb1.arbitrum.io/rpc"))
    parser.add_argument("--pool", required=True)
    parser.add_argument("--quoter", default=DEFAULT_QUOTER)
    parser.add_argument("--token0-coingecko-id", required=True)
    parser.add_argument("--token1-coingecko-id", required=True)
    parser.add_argument("--total-usd", type=float, required=True)
    parser.add_argument("--chunk-usd", type=float, default=1000.0)
    parser.add_argument("--direction", choices=["buy_token0", "sell_token0", "both"], default="both")
    parser.add_argument("--out", default=str(OUTPUTS_DIR / "chunked-trade-analysis.json"))
    args = parser.parse_args()

    rpc_url = args.rpc_url
    pool = args.pool

    token0 = read_pool_token(rpc_url, pool, "token0()")
    token1 = read_pool_token(rpc_url, pool, "token1()")
    dec0 = read_erc20_decimals(rpc_url, token0)
    dec1 = read_erc20_decimals(rpc_url, token1)

    state = read_univ3_pool_state(rpc_url, pool)
    spot_t1_per_t0 = compute_spot_token1_per_token0(state)

    prices = coingecko_simple_price([args.token0_coingecko_id, args.token1_coingecko_id], "usd")
    t0_usd = Decimal(str(prices[args.token0_coingecko_id]["usd"]))
    t1_usd = Decimal(str(prices[args.token1_coingecko_id]["usd"]))

    total_usd = Decimal(str(args.total_usd))
    chunk_usd = Decimal(str(args.chunk_usd))

    directions = ["buy_token0", "sell_token0"] if args.direction == "both" else [args.direction]

    results: dict[str, Any] = {
        "rpc_url": rpc_url,
        "pool": pool,
        "token0": token0,
        "token1": token1,
        "fee": state.fee,
        "spot_token1_per_token0": str(spot_t1_per_t0),
        "prices_usd": {"token0": str(t0_usd), "token1": str(t1_usd)},
        "params": {"total_usd": str(total_usd), "chunk_usd": str(chunk_usd)},
        "directions": {},
    }

    for direction in directions:
        single = simulate_trade(
            rpc_url=rpc_url,
            quoter=args.quoter,
            token0=token0,
            token1=token1,
            dec0=dec0,
            dec1=dec1,
            fee=state.fee,
            spot_t1_per_t0=spot_t1_per_t0,
            t0_usd=t0_usd,
            t1_usd=t1_usd,
            total_usd=total_usd,
            direction=direction,
        )

        chunked = simulate_chunked_reverted(
            rpc_url=rpc_url,
            quoter=args.quoter,
            token0=token0,
            token1=token1,
            dec0=dec0,
            dec1=dec1,
            fee=state.fee,
            spot_t1_per_t0=spot_t1_per_t0,
            t0_usd=t0_usd,
            t1_usd=t1_usd,
            total_usd=total_usd,
            chunk_usd=chunk_usd,
            direction=direction,
        )

        results["directions"][direction] = {
            "single": asdict(single),
            "chunked_reverted": asdict(chunked),
        }

    out_path = Path(args.out)
    write_json(out_path, results)
    print(f"Wrote `{out_path}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

