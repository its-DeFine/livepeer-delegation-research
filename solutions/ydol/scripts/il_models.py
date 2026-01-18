from __future__ import annotations

import argparse
import csv
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from utils import OUTPUTS_DIR, coingecko_market_chart_daily, coingecko_simple_price, write_json


def to_date_map(series: list[list[float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ts_ms, price in series:
        d = datetime.utcfromtimestamp(ts_ms / 1000).date().isoformat()
        out[d] = float(price)
    return out


def il_50_50(relative_price_change: float) -> float:
    # Standard constant-product IL vs 50/50 HODL
    r = relative_price_change
    return 2 * math.sqrt(r) / (1 + r) - 1


def percentiles(values: list[float], ps: list[float]) -> dict[str, float]:
    if not values:
        return {}
    s = sorted(values)
    out: dict[str, float] = {}
    for p in ps:
        idx = int(p * (len(s) - 1))
        out[f"p{int(p*100):02d}"] = s[idx]
    out["best"] = s[-1]
    out["worst"] = s[0]
    return out


@dataclass(frozen=True)
class WindowSummary:
    window_days: int
    samples: int
    il_stats: dict[str, float]
    annualized_vol_ratio: float | None = None


def required_volume_per_day(*, capital_usd: float, il_abs: float, eff_fee: float, window_days: int) -> float:
    fees_needed = il_abs * capital_usd
    total_volume = fees_needed / eff_fee
    return total_volume / window_days


def main() -> int:
    parser = argparse.ArgumentParser(description="Impermanent-loss and breakeven volume models for LPT/ETH exposure.")
    parser.add_argument("--days", type=int, default=365, help="How many days of daily CoinGecko data to pull.")
    parser.add_argument("--capital-usd", type=float, default=1_000_000, help="Assumed deployed capital size for breakeven examples.")
    parser.add_argument("--windows", default="30,90,180,365", help="Comma-separated IL windows (days).")
    parser.add_argument("--fee-tiers", default="0.003,0.01", help="Comma-separated Uniswap fee tiers to model (e.g. 0.003 for 0.30%).")
    parser.add_argument("--dao-fee-shares", default="0.5,0.8", help="Comma-separated DAO shares of earned trading fees (e.g. 0.5 for 50/50).")
    parser.add_argument("--out-json", default=str(OUTPUTS_DIR / "il-model-summary.json"))
    parser.add_argument("--out-csv", default=str(OUTPUTS_DIR / "breakeven-volume.csv"))
    args = parser.parse_args()

    windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]
    fee_tiers = [float(x.strip()) for x in args.fee_tiers.split(",") if x.strip()]
    dao_shares = [float(x.strip()) for x in args.dao_fee_shares.split(",") if x.strip()]

    lpt = to_date_map(coingecko_market_chart_daily("livepeer", days=args.days))
    eth = to_date_map(coingecko_market_chart_daily("ethereum", days=args.days))
    dates = sorted(set(lpt) & set(eth))
    ratios = [lpt[d] / eth[d] for d in dates]

    # Annualized vol of the ratio (log returns)
    log_rets = [math.log(ratios[i] / ratios[i - 1]) for i in range(1, len(ratios)) if ratios[i - 1] > 0 and ratios[i] > 0]
    sigma_daily = statistics.pstdev(log_rets) if log_rets else 0.0
    sigma_annual = sigma_daily * math.sqrt(365)

    window_summaries: list[WindowSummary] = []
    for w in windows:
        ils: list[float] = []
        if w >= len(ratios):
            continue
        if w == len(ratios) - 1:
            r = ratios[-1] / ratios[0]
            ils = [il_50_50(r)]
        else:
            for i in range(0, len(ratios) - w):
                r = ratios[i + w] / ratios[i]
                ils.append(il_50_50(r))
        window_summaries.append(
            WindowSummary(
                window_days=w,
                samples=len(ils),
                il_stats=percentiles(ils, [0.1, 0.5, 0.9]),
                annualized_vol_ratio=sigma_annual if w == windows[0] else None,
            )
        )

    # Build breakeven table: required volume/day to offset IL using fee capture only
    breakeven_rows: list[dict[str, str]] = []
    for ws in window_summaries:
        for stat_name, il in ws.il_stats.items():
            il_abs = max(0.0, -il)
            for tier in fee_tiers:
                for share in dao_shares:
                    eff_fee = tier * share
                    v = required_volume_per_day(
                        capital_usd=args.capital_usd,
                        il_abs=il_abs,
                        eff_fee=eff_fee,
                        window_days=ws.window_days,
                    )
                    breakeven_rows.append(
                        {
                            "window_days": str(ws.window_days),
                            "stat": stat_name,
                            "il_pct": f"{il*100:.4f}",
                            "capital_usd": f"{args.capital_usd:.0f}",
                            "fee_tier": f"{tier:.6f}",
                            "dao_fee_share": f"{share:.3f}",
                            "effective_fee": f"{eff_fee:.6f}",
                            "required_volume_per_day_usd": f"{v:.2f}",
                        }
                    )

    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)

    summary = {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "days": args.days,
        "capital_usd": args.capital_usd,
        "ratio_start_end": {"start": ratios[0], "end": ratios[-1], "change": ratios[-1] / ratios[0]},
        "annualized_vol_ratio": sigma_annual,
        "windows": [asdict(ws) for ws in window_summaries],
    }
    write_json(out_json, summary)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(breakeven_rows[0].keys()))
        writer.writeheader()
        writer.writerows(breakeven_rows)

    # Also dump a quick “net PnL” scenario table at a few volumes for the 180d median vs worst.
    # This is intentionally simple and is meant to highlight asymmetry, not forecast returns.
    prices = coingecko_simple_price(["livepeer", "ethereum"], "usd")
    lpt_usd = Decimal(str(prices["livepeer"]["usd"]))
    eth_usd = Decimal(str(prices["ethereum"]["usd"]))
    print(f"CoinGecko snapshot: LPT=${lpt_usd} ETH=${eth_usd}")
    print(f"Wrote `{out_json}` and `{out_csv}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
