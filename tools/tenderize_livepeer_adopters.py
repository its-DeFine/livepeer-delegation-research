#!/usr/bin/env python3

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen


DEPOSIT_TOPIC0 = "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c"  # Deposit(address,uint256)
UNSTAKE_TOPIC0 = "0x18edd09e80386cd99df397e2e0d87d2bb259423eae08645e776321a36fe680ef"  # Unstake(address,address,uint256,uint256)
WITHDRAW_TOPIC0 = "0xf279e6a1f5e320cca91135676d9cb6e44ca8a08c0b88342bcdb1144f6511b568"  # Withdraw(address,uint256,uint256)
ERC20_TRANSFER_TOPIC0 = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)


TENDERIZE_LIVEPEER_ARBITRUM = {
    "chain": "arbitrum-one",
    "rpc_url_default": "https://arb1.arbitrum.io/rpc",
    "deployment_tx": "0x5c38f744c68e188751e275b0a599d0eec3745829a226641430965117295aadea",
    "deployment_block": 11600821,
    "contracts": {
        "tenderizer": "0x339efC059C6D4Aa50a41F8246a017B57Aa477b60",
        "tender_token_tlpt": "0xfaC38532829fDD744373fdcd4708Ab90fA0c4078",
        "lpt": "0x289ba1701C2F088cf0faf8B3705246331cB8A839",
        "tender_swap": "0x2429fC7082eb517C14946b392b195B181D0b9781",
        "lp_token": "0x6cAbc6e78c1D632b6210EaB71c19889b92376931",
        "tender_farm": "0x3FE01e8b62a8E17F296Eb3832504C3D3A49f2209",
    },
}


def _as_hex_block(block: int) -> str:
    return hex(block)


def _topic_to_address(topic_hex: str) -> str:
    topic_hex = topic_hex.lower()
    if topic_hex.startswith("0x"):
        topic_hex = topic_hex[2:]
    if len(topic_hex) != 64:
        raise ValueError(f"unexpected topic length for address topic: {len(topic_hex)}")
    return "0x" + topic_hex[-40:]


def _data_to_uint256(data_hex: str) -> int:
    data_hex = data_hex.lower()
    if data_hex.startswith("0x"):
        data_hex = data_hex[2:]
    if data_hex == "":
        return 0
    return int(data_hex, 16)


def _rpc(url: str, method: str, params: List[Any], request_id: int = 1) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode("utf-8")
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"rpc error calling {method}: {exc}") from exc

    out = json.loads(body)
    if "error" in out:
        raise RuntimeError(f"rpc error calling {method}: {out['error']}")
    return out["result"]


def _get_latest_block(rpc_url: str) -> int:
    return int(_rpc(rpc_url, "eth_blockNumber", []), 16)


def _get_block_timestamp(rpc_url: str, block_number: int) -> int:
    block = _rpc(rpc_url, "eth_getBlockByNumber", [_as_hex_block(block_number), False])
    return int(block["timestamp"], 16)


def _get_logs(
    rpc_url: str,
    address: str,
    topics: List[Optional[str]],
    from_block: int,
    to_block: int,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "address": address,
        "fromBlock": _as_hex_block(from_block),
        "toBlock": _as_hex_block(to_block),
        "topics": topics,
    }
    return _rpc(rpc_url, "eth_getLogs", [params])


@dataclass
class FlowStats:
    event_count: int = 0
    total_amount: int = 0
    first_block: Optional[int] = None
    last_block: Optional[int] = None

    def add(self, block_number: int, amount: int) -> None:
        self.event_count += 1
        self.total_amount += amount
        if self.first_block is None or block_number < self.first_block:
            self.first_block = block_number
        if self.last_block is None or block_number > self.last_block:
            self.last_block = block_number


def _scan_event(
    rpc_url: str,
    address: str,
    topic0: str,
    from_block: int,
    to_block: int,
    step: int,
) -> List[Dict[str, Any]]:
    logs: List[Dict[str, Any]] = []

    start = from_block
    current_step = step
    chunk_i = 0
    while start <= to_block:
        end = min(start + current_step - 1, to_block)
        try:
            t0 = time.time()
            chunk = _get_logs(rpc_url, address, [topic0], start, end)
            dt = time.time() - t0
            logs.extend(chunk)
            chunk_i += 1
            print(
                f"[{chunk_i}] blocks {start:,}..{end:,}: {len(chunk)} logs (step={current_step:,}, {dt:.2f}s)",
                file=sys.stderr,
            )
            start = end + 1
        except RuntimeError as exc:
            msg = str(exc).lower()
            # Common RPC limits: "query returned more than 10000 results", "response too large", etc.
            if any(x in msg for x in ["more than", "too large", "limit", "timeout"]) and current_step > 1_000:
                current_step = max(current_step // 2, 1_000)
                continue
            raise

    return logs


def _human_lpt(amount_wei: int) -> float:
    # LPT uses 18 decimals.
    return amount_wei / 1e18


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Tenderize Livepeer (Arbitrum) adoption from on-chain logs.")
    parser.add_argument("--rpc-url", default=TENDERIZE_LIVEPEER_ARBITRUM["rpc_url_default"])
    parser.add_argument("--from-block", type=int, default=TENDERIZE_LIVEPEER_ARBITRUM["deployment_block"])
    parser.add_argument("--to-block", type=int, default=0, help="Default: latest")
    parser.add_argument("--step", type=int, default=5_000_000)
    parser.add_argument("--out-json", default="", help="Write summary JSON to this path")
    parser.add_argument("--include-transfer-holders", action="store_true", help="Count unique tLPT holders (heavier).")

    args = parser.parse_args()

    tenderizer = TENDERIZE_LIVEPEER_ARBITRUM["contracts"]["tenderizer"]
    tender_token = TENDERIZE_LIVEPEER_ARBITRUM["contracts"]["tender_token_tlpt"]

    latest = args.to_block or _get_latest_block(args.rpc_url)
    print(f"Scanning Tenderize Livepeer tenderizer {tenderizer} from {args.from_block} to {latest}...", file=sys.stderr)

    deposit_logs = _scan_event(args.rpc_url, tenderizer, DEPOSIT_TOPIC0, args.from_block, latest, args.step)
    unstake_logs = _scan_event(args.rpc_url, tenderizer, UNSTAKE_TOPIC0, args.from_block, latest, args.step)
    withdraw_logs = _scan_event(args.rpc_url, tenderizer, WITHDRAW_TOPIC0, args.from_block, latest, args.step)

    deposits_by_addr: Dict[str, FlowStats] = defaultdict(FlowStats)
    unstakes_by_addr: Dict[str, FlowStats] = defaultdict(FlowStats)
    withdraws_by_addr: Dict[str, FlowStats] = defaultdict(FlowStats)

    for log in deposit_logs:
        addr = _topic_to_address(log["topics"][1])
        amount = _data_to_uint256(log["data"])
        deposits_by_addr[addr].add(int(log["blockNumber"], 16), amount)

    for log in unstake_logs:
        addr = _topic_to_address(log["topics"][1])
        # data encodes amount + lock id. amount is first 32 bytes.
        data = log["data"][2:]
        amount = int(data[:64], 16) if data else 0
        unstakes_by_addr[addr].add(int(log["blockNumber"], 16), amount)

    for log in withdraw_logs:
        addr = _topic_to_address(log["topics"][1])
        data = log["data"][2:]
        amount = int(data[:64], 16) if data else 0
        withdraws_by_addr[addr].add(int(log["blockNumber"], 16), amount)

    def _range_from_stats(stats: Iterable[FlowStats]) -> Tuple[Optional[int], Optional[int]]:
        first: Optional[int] = None
        last: Optional[int] = None
        for s in stats:
            if s.first_block is not None and (first is None or s.first_block < first):
                first = s.first_block
            if s.last_block is not None and (last is None or s.last_block > last):
                last = s.last_block
        return first, last

    dep_first, dep_last = _range_from_stats(deposits_by_addr.values())
    w_first, w_last = _range_from_stats(withdraws_by_addr.values())

    summary: Dict[str, Any] = {
        "tenderize_livepeer": TENDERIZE_LIVEPEER_ARBITRUM,
        "window": {
            "from_block": args.from_block,
            "to_block": latest,
        },
        "deposit": {
            "event_count": len(deposit_logs),
            "unique_depositors": len(deposits_by_addr),
            "total_deposited_lpt": sum(_human_lpt(s.total_amount) for s in deposits_by_addr.values()),
            "first_block": dep_first,
            "last_block": dep_last,
        },
        "unstake": {
            "event_count": len(unstake_logs),
            "unique_unstakers": len(unstakes_by_addr),
            "total_unstaked_lpt": sum(_human_lpt(s.total_amount) for s in unstakes_by_addr.values()),
        },
        "withdraw": {
            "event_count": len(withdraw_logs),
            "unique_withdrawers": len(withdraws_by_addr),
            "total_withdrawn_lpt": sum(_human_lpt(s.total_amount) for s in withdraws_by_addr.values()),
            "first_block": w_first,
            "last_block": w_last,
        },
    }

    if dep_first is not None:
        summary["deposit"]["first_ts"] = _get_block_timestamp(args.rpc_url, dep_first)
    if dep_last is not None:
        summary["deposit"]["last_ts"] = _get_block_timestamp(args.rpc_url, dep_last)
    if w_first is not None:
        summary["withdraw"]["first_ts"] = _get_block_timestamp(args.rpc_url, w_first)
    if w_last is not None:
        summary["withdraw"]["last_ts"] = _get_block_timestamp(args.rpc_url, w_last)

    top_depositors = sorted(deposits_by_addr.items(), key=lambda kv: kv[1].total_amount, reverse=True)[:25]
    summary["deposit"]["top_depositors"] = [
        {
            "address": addr,
            "deposit_events": stats.event_count,
            "total_deposited_lpt": _human_lpt(stats.total_amount),
            "first_block": stats.first_block,
            "last_block": stats.last_block,
        }
        for addr, stats in top_depositors
    ]

    depositor_addrs = set(deposits_by_addr.keys())
    unstaker_addrs = set(unstakes_by_addr.keys())
    withdrawer_addrs = set(withdraws_by_addr.keys())
    summary["deposit"]["depositors_with_unstake"] = len(depositor_addrs & unstaker_addrs)
    summary["deposit"]["depositors_with_withdraw"] = len(depositor_addrs & withdrawer_addrs)

    # Deposit size distribution (by depositor total deposited).
    depositor_totals = [_human_lpt(stats.total_amount) for stats in deposits_by_addr.values()]
    depositor_totals.sort()

    def _bucket_counts(values: List[float], cutoffs: List[float]) -> Dict[str, int]:
        buckets: Dict[str, int] = {}
        prev: Optional[float] = None
        for cutoff in cutoffs:
            if prev is None:
                label = f"<= {cutoff}"
            else:
                label = f"{prev} - {cutoff}"
            buckets[label] = 0
            prev = cutoff
        buckets[f"> {cutoffs[-1]}"] = 0

        for v in values:
            prev = None
            placed = False
            for cutoff in cutoffs:
                if v <= cutoff:
                    if prev is None:
                        label = f"<= {cutoff}"
                    else:
                        label = f"{prev} - {cutoff}"
                    buckets[label] += 1
                    placed = True
                    break
                prev = cutoff
            if not placed:
                buckets[f"> {cutoffs[-1]}"] += 1
        return buckets

    if depositor_totals:
        cutoffs = [1, 10, 100, 1_000, 10_000]
        summary["deposit"]["depositor_total_deposit_buckets"] = _bucket_counts(depositor_totals, cutoffs)

        def _percentile(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            k = (len(values) - 1) * p
            f = int(k)
            c = min(f + 1, len(values) - 1)
            if f == c:
                return float(values[f])
            d0 = values[f] * (c - k)
            d1 = values[c] * (k - f)
            return float(d0 + d1)

        summary["deposit"]["depositor_total_deposit_percentiles"] = {
            "p50": _percentile(depositor_totals, 0.50),
            "p75": _percentile(depositor_totals, 0.75),
            "p90": _percentile(depositor_totals, 0.90),
            "p95": _percentile(depositor_totals, 0.95),
            "p99": _percentile(depositor_totals, 0.99),
        }

    # Net flow proxy (withdrawn - deposited) on a per-depositor basis.
    withdrawn_by_addr_lpt = {addr: _human_lpt(stats.total_amount) for addr, stats in withdraws_by_addr.items()}
    deposited_by_addr_lpt = {addr: _human_lpt(stats.total_amount) for addr, stats in deposits_by_addr.items()}
    net = []
    for addr in depositor_addrs:
        deposited = deposited_by_addr_lpt.get(addr, 0.0)
        withdrawn = withdrawn_by_addr_lpt.get(addr, 0.0)
        net.append((addr, withdrawn - deposited))
    net.sort(key=lambda x: x[1], reverse=True)
    summary["deposit"]["withdraw_minus_deposit_top25"] = [{"address": a, "lpt": v} for a, v in net[:25]]
    summary["deposit"]["withdraw_minus_deposit_bottom25"] = [{"address": a, "lpt": v} for a, v in net[-25:]]

    if args.include_transfer_holders:
        print(f"Scanning tLPT Transfer logs for {tender_token} (may take longer)...", file=sys.stderr)
        transfer_logs = _scan_event(args.rpc_url, tender_token, ERC20_TRANSFER_TOPIC0, args.from_block, latest, args.step)
        holders = set()
        for log in transfer_logs:
            # topics[1] = from, topics[2] = to
            holders.add(_topic_to_address(log["topics"][1]))
            holders.add(_topic_to_address(log["topics"][2]))
        summary["tLPT_transfer"] = {
            "event_count": len(transfer_logs),
            "unique_addresses_involved": len(holders),
        }

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, sort_keys=True)
            f.write("\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
