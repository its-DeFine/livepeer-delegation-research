from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Case:
    id: str
    name: str
    rpc_url: str
    pool: str
    token0_coingecko_id: str
    token1_coingecko_id: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Run standardized onchain analytics across a set of Uniswap v3 pools.")
    parser.add_argument("--cases", default=str(ROOT / "cases" / "cases.json"))
    parser.add_argument("--amounts-usd", default="1000,5000,10000,25000,50000")
    parser.add_argument("--swap-windows-days", default="1,30")
    parser.add_argument("--dao-fee-splits", default="0.5,0.8", help="DAO share of trading fees, for illustrative net-fee calculations.")
    parser.add_argument("--refresh", action="store_true", help="Re-run even if outputs already exist.")
    args = parser.parse_args()

    cases_data = read_json(Path(args.cases))
    cases = [
        Case(
            id=c["id"],
            name=c["name"],
            rpc_url=c["rpc_url"],
            pool=c["pool"],
            token0_coingecko_id=c["token0_coingecko_id"],
            token1_coingecko_id=c["token1_coingecko_id"],
        )
        for c in cases_data["cases"]
    ]

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "cases").mkdir(parents=True, exist_ok=True)

    windows = [float(x.strip()) for x in args.swap_windows_days.split(",") if x.strip()]

    for case in cases:
        slug = case.id
        slippage_csv = OUTPUTS / "cases" / f"{slug}-slippage.csv"
        slippage_json = OUTPUTS / "cases" / f"{slug}-slippage.json"
        if args.refresh or not slippage_json.exists():
            run(
                [
                    "python3",
                    str(SCRIPTS / "univ3_slippage_table.py"),
                    "--rpc-url",
                    case.rpc_url,
                    "--pool",
                    case.pool,
                    "--token0-coingecko-id",
                    case.token0_coingecko_id,
                    "--token1-coingecko-id",
                    case.token1_coingecko_id,
                    "--amounts-usd",
                    args.amounts_usd,
                    "--out-csv",
                    str(slippage_csv),
                    "--out-json",
                    str(slippage_json),
                ]
            )

        for d in windows:
            suffix = f"{d:g}d".replace(".", "p")
            swap_json = OUTPUTS / "cases" / f"{slug}-swap-analytics-{suffix}.json"
            if args.refresh or not swap_json.exists():
                run(
                    [
                        "python3",
                        str(SCRIPTS / "univ3_swap_analytics.py"),
                        "--rpc-url",
                        case.rpc_url,
                        "--pool",
                        case.pool,
                        "--token0-coingecko-id",
                        case.token0_coingecko_id,
                        "--token1-coingecko-id",
                        case.token1_coingecko_id,
                        "--days",
                        str(d),
                        "--out",
                        str(swap_json),
                    ]
                )

    # Generate markdown summary
    fee_splits = [float(x.strip()) for x in args.dao_fee_splits.split(",") if x.strip()]
    report_lines = ["# Arrakis case studies (pool-level)", ""]
    report_lines.append(
        "These are pool-level metrics (slippage + recent onchain volume/fees) for pools associated with prior Arrakis/PALM-style proposals. "
        "They do **not** attribute outcomes to a specific Arrakis vault without vault addresses / share-of-liquidity data."
    )
    report_lines.append("")

    report_lines.append("## Summary table (24h window)")
    report_lines.append("")
    report_lines.append("| Case | Pool | Fee tier | 24h volume (USD) | 24h fees (USD) | $25k buy impact | $25k sell impact |")
    report_lines.append("|---|---|---:|---:|---:|---:|---:|")

    for case in cases:
        slug = case.id
        slippage = read_json(OUTPUTS / "cases" / f"{slug}-slippage.json")
        swap_1d = read_json(OUTPUTS / "cases" / f"{slug}-swap-analytics-1d.json")

        fee = float(slippage["fee"]) / 1_000_000
        vol = float(swap_1d["aggregate"]["volume_usd"])
        fees = float(swap_1d["aggregate"]["fees_usd"])

        # find 25k row if present
        buy_25 = sell_25 = float("nan")
        for row in slippage["rows"]:
            if row["amount_usd"] == "25000":
                buy_25 = float(row["buy_token0_impact_pct"])
                sell_25 = float(row["sell_token0_impact_pct"])
                break

        report_lines.append(
            f"| {case.name} | `{case.pool}` | {fee:.2%} | ${vol:,.0f} | ${fees:,.0f} | {buy_25:.2f}% | {sell_25:.2f}% |"
        )

    report_lines.append("")
    report_lines.append("## Fee split sensitivity (illustrative)")
    report_lines.append("")
    report_lines.append("Assumes fees are paid pro-rata to the protocol-owned LP, and shows how much of pool fees the DAO retains under different splits.")
    report_lines.append("")
    report_lines.append("| Case | 24h pool fees (USD) | " + " | ".join([f"DAO {int(s*100)}%" for s in fee_splits]) + " |")
    report_lines.append("|---|---:|" + "|".join(["---:"] * len(fee_splits)) + "|")
    for case in cases:
        slug = case.id
        swap_1d = read_json(OUTPUTS / "cases" / f"{slug}-swap-analytics-1d.json")
        fees = float(swap_1d["aggregate"]["fees_usd"])
        splits = " | ".join([f"${fees*s:,.0f}" for s in fee_splits])
        report_lines.append(f"| {case.name} | ${fees:,.0f} | {splits} |")

    out_report = REPORTS / "arrakis-case-studies.md"
    out_report.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")
    print(f"Wrote `{out_report}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
