#!/usr/bin/env python3
"""
Livepeer — Buy pressure proxies (exchange outflows → bonders).

Why this exists
---------------
Most "buy pressure" for LPT happens off-chain (CEX order books), which is not directly visible on-chain.
But we can still measure *on-chain proxies* that are consistent with exchange withdrawals that later
become stake:

1) L1 flows from *labeled exchange hot wallets* to recipient wallets ("exchange outflows").
2) Whether those recipient wallets subsequently bond on Arbitrum (Livepeer staking), and how soon.
3) Whether those recipient wallets overlap with cashout-heavy cohorts (sell-pressure proxies).

This is not definitive proof of "buyers" or delta-neutral behavior; it's a measurable, reproducible
signal that can be combined with other evidence packs.

Inputs
------
- `data/labels.json` (exchange + bridge labels; best-effort)
- `data/arbitrum_delegator_addresses.json` (historical delegator set on Arbitrum)
- `artifacts/delegator-bonded-amounts-cache.json` (current bonded stake snapshot, Arbitrum)
- `research/extraction-fingerprints.json` (optional, for cross-reference)

Outputs
-------
- `research/buy-pressure-proxies.json`
- `research/buy-pressure-proxies.md`
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

ETHEREUM_RPC_DEFAULT = "https://rpc.flashbots.net"
ARBITRUM_RPC_DEFAULT = "https://arb1.arbitrum.io/rpc"

LPT_TOKEN_L1 = "0x58b6a8a3302369daec383334672404ee733ab239"
LIVEPEER_BONDING_MANAGER_ARB = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"

# ERC20 Transfer(address indexed from, address indexed to, uint256 value)
TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# cast sig-event "Bond(address,address,address,uint256,uint256)"
TOPIC0_BOND = "0xe5917769f276ddca9f2ee7c6b0b33e1d1e1b61008010ce622c632dd20d168a23"

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


class RpcError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/buy-pressure-proxies"):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self.user_agent = user_agent
        self._id = 0

    def call(self, method: str, params: list) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": self.user_agent},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except HTTPError as e:
            retry_after_s: int | None = None
            try:
                ra = e.headers.get("Retry-After")
                if isinstance(ra, str) and ra.strip().isdigit():
                    retry_after_s = int(ra.strip())
            except Exception:
                retry_after_s = None
            raise RpcError(
                f"HTTP {e.code}: {e.reason}",
                status_code=int(getattr(e, "code", 0)) or None,
                retry_after_s=retry_after_s,
            ) from e
        except URLError as e:
            raise RpcError(f"URL error: {e.reason}") from e
        except Exception as e:
            raise RpcError(f"RPC transport error: {e}") from e

        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise RpcError(f"invalid JSON-RPC response: {raw[:200]!r}") from e

        if isinstance(data, dict) and data.get("error"):
            raise RpcError(str(data["error"]))
        return data.get("result") if isinstance(data, dict) else data


def _rpc_with_retries(client: RpcClient, method: str, params: list, *, max_tries: int = 8) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return client.call(method, params)
        except RpcError as e:
            msg = str(e).lower()
            retryable_http = getattr(e, "status_code", None) in (429, 502, 503, 504)
            retryable = any(
                s in msg
                for s in (
                    "timeout",
                    "timed out",
                    "too many requests",
                    "rate limit",
                    "temporarily unavailable",
                    "service unavailable",
                    "bad gateway",
                    "gateway timeout",
                    "connection reset",
                    "internal error",
                )
            )
            if (not retryable and not retryable_http) or attempt == max_tries:
                raise

            sleep_s = min(2 ** (attempt - 1), 30.0)
            retry_after_s = getattr(e, "retry_after_s", None)
            if isinstance(retry_after_s, int) and retry_after_s > 0:
                sleep_s = max(sleep_s, float(retry_after_s))
            sleep_s = sleep_s * (1 + random.uniform(-0.15, 0.15))
            time.sleep(max(0.5, sleep_s))


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _pad_topic_address(addr: str) -> str:
    a = _normalize_address(addr)
    return "0x" + ("0" * 24) + a[2:]


def _topic_to_address(topic: str) -> str:
    t = str(topic).lower()
    if not t.startswith("0x") or len(t) != 66:
        raise ValueError(f"invalid topic address: {topic}")
    return "0x" + t[-40:]


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _is_chunkable_logs_error(err_msg: str) -> bool:
    msg = err_msg.lower()
    return any(
        s in msg
        for s in (
            "block range",
            "too large",
            "query returned more than",
            "response size",
            "log response size",
            "too many results",
            "more than",
        )
    )


def _get_logs(client: RpcClient, *, address: str, topics: list, from_block: int, to_block: int) -> List[Dict[str, Any]]:
    return _rpc_with_retries(
        client,
        "eth_getLogs",
        [
            {
                "address": address,
                "fromBlock": hex(int(from_block)),
                "toBlock": hex(int(to_block)),
                "topics": topics,
            }
        ],
    )


def _get_logs_range(
    client: RpcClient,
    *,
    address: str,
    topics: list,
    from_block: int,
    to_block: int,
    max_splits: int = 18,
) -> List[Dict[str, Any]]:
    try:
        return _get_logs(client, address=address, topics=topics, from_block=from_block, to_block=to_block)
    except RpcError as e:
        msg = str(e)
        if not _is_chunkable_logs_error(msg) or max_splits <= 0 or from_block >= to_block:
            raise
        mid = (from_block + to_block) // 2
        left = _get_logs_range(
            client,
            address=address,
            topics=topics,
            from_block=from_block,
            to_block=mid,
            max_splits=max_splits - 1,
        )
        right = _get_logs_range(
            client,
            address=address,
            topics=topics,
            from_block=mid + 1,
            to_block=to_block,
            max_splits=max_splits - 1,
        )
        return left + right


def _get_block_number(client: RpcClient) -> int:
    return int(_rpc_with_retries(client, "eth_blockNumber", []), 16)


def _get_block_timestamp_s(client: RpcClient, block_number: int, cache: Dict[int, int]) -> int:
    if block_number in cache:
        return cache[block_number]
    blk = _rpc_with_retries(client, "eth_getBlockByNumber", [hex(int(block_number)), False])
    if not isinstance(blk, dict) or "timestamp" not in blk:
        raise RpcError(f"invalid block response for {block_number}")
    ts = int(str(blk["timestamp"]), 16)
    cache[block_number] = ts
    return ts


def _iso(ts_s: int) -> str:
    return datetime.fromtimestamp(int(ts_s), tz=timezone.utc).isoformat()


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _load_labels(path: str) -> Dict[str, Dict[str, Any]]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"labels file must be object: {path}")
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        try:
            out[_normalize_address(k)] = v
        except ValueError:
            continue
    return out


def _labels_by_category(labels: Dict[str, Dict[str, Any]], category: str) -> List[str]:
    addrs: List[str] = []
    for a, meta in labels.items():
        if meta.get("category") == category:
            addrs.append(a)
    return sorted(set(addrs))


def _label_name(labels: Dict[str, Dict[str, Any]], addr: str) -> str:
    meta = labels.get(addr) or {}
    if isinstance(meta, dict) and isinstance(meta.get("name"), str):
        return str(meta["name"])
    return addr


def _label_exchange(labels: Dict[str, Dict[str, Any]], addr: str) -> str:
    meta = labels.get(addr) or {}
    if isinstance(meta, dict) and isinstance(meta.get("exchange"), str):
        return str(meta["exchange"])
    return "unknown"


@dataclass
class RecipientAgg:
    inbound_wei: int = 0
    inbound_txs: int = 0
    first_block: int = 0
    last_block: int = 0
    sources_wei_by_exchange: Dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.sources_wei_by_exchange is None:
            self.sources_wei_by_exchange = {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eth-rpc", default=os.environ.get("ETH_RPC_URL") or ETHEREUM_RPC_DEFAULT)
    parser.add_argument("--arb-rpc", default=os.environ.get("ARB_RPC_URL") or ARBITRUM_RPC_DEFAULT)
    parser.add_argument("--labels-json", default="data/labels.json")
    parser.add_argument("--delegators-json", default="data/arbitrum_delegator_addresses.json")
    parser.add_argument("--bonded-cache-json", default="artifacts/delegator-bonded-amounts-cache.json")
    parser.add_argument("--cashout-json", default="research/extraction-fingerprints.json")

    parser.add_argument("--l1-from-block", type=int, default=14_600_000)
    parser.add_argument("--l1-to-block", type=int, default=0, help="0 = latest")

    parser.add_argument("--arb-from-block", type=int, default=0)
    parser.add_argument("--arb-to-block", type=int, default=0, help="0 = latest")

    parser.add_argument("--min-inbound-lpt", type=Decimal, default=Decimal("10000"))
    parser.add_argument("--max-recipients", type=int, default=200)
    parser.add_argument("--bond-window-days", type=int, default=30)
    parser.add_argument("--recipient-outflow-top-n", type=int, default=100)

    parser.add_argument("--out-json", default="research/buy-pressure-proxies.json")
    parser.add_argument("--out-md", default="research/buy-pressure-proxies.md")
    args = parser.parse_args()

    labels = _load_labels(args.labels_json)
    exchange_wallets = _labels_by_category(labels, "exchange")
    bridge_addrs = _labels_by_category(labels, "bridge")
    livepeer_contract_addrs = _labels_by_category(labels, "livepeer_contract")

    if not exchange_wallets:
        raise SystemExit("no exchange addresses found in labels.json")

    eth = RpcClient(str(args.eth_rpc), user_agent="livepeer-delegation-research/buy-pressure-proxies-l1")
    arb = RpcClient(str(args.arb_rpc), user_agent="livepeer-delegation-research/buy-pressure-proxies-l2")

    l1_to_block = int(args.l1_to_block)
    if l1_to_block <= 0:
        l1_to_block = _get_block_number(eth)
    l1_from_block = int(args.l1_from_block)
    if l1_from_block <= 0 or l1_from_block > l1_to_block:
        raise SystemExit("invalid --l1-from-block/--l1-to-block")

    arb_to_block = int(args.arb_to_block)
    if arb_to_block <= 0:
        arb_to_block = _get_block_number(arb)
    arb_from_block = int(args.arb_from_block)
    if arb_from_block < 0 or arb_from_block > arb_to_block:
        raise SystemExit("invalid --arb-from-block/--arb-to-block")

    delegator_set: set[str] = set()
    raw_delegators = _load_json(args.delegators_json)
    delegator_addrs: Any = raw_delegators
    if isinstance(raw_delegators, dict):
        # Newer format in this repo: { ..., "delegators_count": N, "addresses": [...] }
        delegator_addrs = raw_delegators.get("addresses")
    if isinstance(delegator_addrs, list):
        for a in delegator_addrs:
            if not isinstance(a, str):
                continue
            try:
                delegator_set.add(_normalize_address(a))
            except ValueError:
                continue

    bonded_cache = _load_json(args.bonded_cache_json)
    bonded_wei_by_addr: Dict[str, int] = {}
    if isinstance(bonded_cache, dict) and isinstance(bonded_cache.get("bonded_amount_wei_by_address"), dict):
        for k, v in bonded_cache["bonded_amount_wei_by_address"].items():
            if not isinstance(k, str):
                continue
            try:
                kk = _normalize_address(k)
            except ValueError:
                continue
            try:
                bonded_wei_by_addr[kk] = int(v)
            except Exception:
                continue

    cashout_rank_by_addr: Dict[str, int] = {}
    cashout_archetype_by_addr: Dict[str, str] = {}
    if args.cashout_json and os.path.exists(args.cashout_json):
        cash = _load_json(args.cashout_json)
        wallets = cash.get("wallets") if isinstance(cash, dict) else None
        if isinstance(wallets, list):
            for w in wallets:
                if not isinstance(w, dict):
                    continue
                addr = w.get("address")
                if not isinstance(addr, str):
                    continue
                try:
                    a = _normalize_address(addr)
                except ValueError:
                    continue
                try:
                    cashout_rank_by_addr[a] = int(w.get("rank") or 0)
                except Exception:
                    cashout_rank_by_addr[a] = 0
                if isinstance(w.get("archetype"), str):
                    cashout_archetype_by_addr[a] = str(w["archetype"])

    # Scan L1 exchange outflows (LPT Transfer logs where topic1=exchange).
    recipients: Dict[str, RecipientAgg] = {}
    labeled_outflows_wei_by_category: Dict[str, int] = defaultdict(int)
    outflows_wei_by_exchange_group: Dict[str, int] = defaultdict(int)
    total_logs = 0

    for idx, ex_addr in enumerate(exchange_wallets, start=1):
        ex_group = _label_exchange(labels, ex_addr)
        ex_name = _label_name(labels, ex_addr)
        print(f"[{idx}/{len(exchange_wallets)}] scanning {ex_group}: {ex_name} ({ex_addr}) …")

        topics = [TOPIC0_TRANSFER, _pad_topic_address(ex_addr)]
        logs = _get_logs_range(
            eth,
            address=LPT_TOKEN_L1,
            topics=topics,
            from_block=l1_from_block,
            to_block=l1_to_block,
        )
        total_logs += len(logs)

        for log in logs:
            try:
                to_addr = _normalize_address(_topic_to_address(log["topics"][2]))
            except Exception:
                continue
            try:
                value_wei = int(str(log.get("data") or "0x0"), 16)
            except Exception:
                continue
            try:
                block_no = int(str(log.get("blockNumber") or "0x0"), 16)
            except Exception:
                continue

            if to_addr == ZERO_ADDRESS:
                labeled_outflows_wei_by_category["burn"] += value_wei
                continue

            meta = labels.get(to_addr) or {}
            cat = meta.get("category") if isinstance(meta, dict) else None
            if isinstance(cat, str) and cat:
                labeled_outflows_wei_by_category[cat] += value_wei
                continue

            agg = recipients.get(to_addr)
            if agg is None:
                agg = RecipientAgg(inbound_wei=0, inbound_txs=0, first_block=block_no, last_block=block_no)
                recipients[to_addr] = agg

            agg.inbound_wei += value_wei
            agg.inbound_txs += 1
            agg.first_block = min(agg.first_block, block_no) if agg.first_block else block_no
            agg.last_block = max(agg.last_block, block_no)
            if agg.sources_wei_by_exchange is not None:
                agg.sources_wei_by_exchange[ex_group] = int(agg.sources_wei_by_exchange.get(ex_group, 0)) + value_wei
            outflows_wei_by_exchange_group[ex_group] += value_wei

    # Rank recipients by inbound LPT.
    ranked: List[Tuple[str, RecipientAgg, Decimal]] = []
    for addr, agg in recipients.items():
        inbound_lpt = _wei_to_lpt(agg.inbound_wei)
        if inbound_lpt >= args.min_inbound_lpt:
            ranked.append((addr, agg, inbound_lpt))
    ranked.sort(key=lambda t: t[2], reverse=True)
    ranked = ranked[: int(args.max_recipients)]

    eth_block_ts_cache: Dict[int, int] = {}
    arb_block_ts_cache: Dict[int, int] = {}

    # Prepare per-recipient rows.
    rows: List[Dict[str, Any]] = []
    for rank, (addr, agg, inbound_lpt) in enumerate(ranked, start=1):
        first_ts = _get_block_timestamp_s(eth, agg.first_block, eth_block_ts_cache)
        last_ts = _get_block_timestamp_s(eth, agg.last_block, eth_block_ts_cache)

        sources = agg.sources_wei_by_exchange or {}
        top_sources = sorted(sources.items(), key=lambda kv: kv[1], reverse=True)[:3]
        top_sources_fmt = [{"exchange": k, "inbound_lpt": str(_wei_to_lpt(v))} for k, v in top_sources]

        is_delegator = addr in delegator_set
        bonded_now = _wei_to_lpt(int(bonded_wei_by_addr.get(addr, 0)))

        rows.append(
            {
                "rank": rank,
                "address": addr,
                "exchange_inbound_lpt": str(inbound_lpt),
                "inbound_txs": int(agg.inbound_txs),
                "first_inbound_block": int(agg.first_block),
                "last_inbound_block": int(agg.last_block),
                "first_inbound_time": _iso(first_ts),
                "last_inbound_time": _iso(last_ts),
                "top_sources": top_sources_fmt,
                "is_arbitrum_delegator": bool(is_delegator),
                "bonded_now_lpt": str(bonded_now),
                "cashout_fingerprint_rank": int(cashout_rank_by_addr.get(addr, 0)),
                "cashout_archetype": cashout_archetype_by_addr.get(addr, ""),
            }
        )

    # Bond timing: fetch Bond logs for candidate recipients that are delegators.
    candidate_delegators = [r["address"] for r in rows if r.get("is_arbitrum_delegator")]
    delegator_to_rows: Dict[str, Dict[str, Any]] = {r["address"]: r for r in rows}

    if candidate_delegators:
        print(f"fetching Bond logs for {len(candidate_delegators)} candidate delegators on Arbitrum …")
        batch_size = 60
        for start in range(0, len(candidate_delegators), batch_size):
            batch = candidate_delegators[start : start + batch_size]
            topic3_list = [_pad_topic_address(a) for a in batch]
            topics = [TOPIC0_BOND, None, None, topic3_list]
            logs = _get_logs_range(
                arb,
                address=LIVEPEER_BONDING_MANAGER_ARB,
                topics=topics,
                from_block=arb_from_block,
                to_block=arb_to_block,
            )
            blocks_by_addr: Dict[str, List[int]] = defaultdict(list)
            for log in logs:
                try:
                    delegator = _normalize_address(_topic_to_address(log["topics"][3]))
                except Exception:
                    continue
                try:
                    bn = int(str(log.get("blockNumber") or "0x0"), 16)
                except Exception:
                    continue
                blocks_by_addr[delegator].append(bn)

            for delegator, blocks in blocks_by_addr.items():
                if delegator not in delegator_to_rows:
                    continue
                bsorted = sorted(set(int(b) for b in blocks))
                if not bsorted:
                    continue

                row = delegator_to_rows[delegator]
                inflow_ts = datetime.fromisoformat(str(row["first_inbound_time"])).timestamp()

                first_bond_block = int(bsorted[0])
                first_bond_ts = _get_block_timestamp_s(arb, first_bond_block, arb_block_ts_cache)
                row["first_bond_block"] = first_bond_block
                row["first_bond_time"] = _iso(first_bond_ts)
                row["bonded_before_inflow"] = bool(first_bond_ts < inflow_ts)

                bond_after_block: Optional[int] = None
                bond_after_ts: Optional[int] = None
                for bn in bsorted:
                    ts = _get_block_timestamp_s(arb, int(bn), arb_block_ts_cache)
                    if ts >= inflow_ts:
                        bond_after_block = int(bn)
                        bond_after_ts = int(ts)
                        break

                if bond_after_block is not None and bond_after_ts is not None:
                    row["first_bond_after_inflow_block"] = int(bond_after_block)
                    row["first_bond_after_inflow_time"] = _iso(bond_after_ts)
                    delta_days = Decimal(str(bond_after_ts - inflow_ts)) / Decimal(86400)
                    row["bond_after_inflow_days"] = str(delta_days)
                    row["bonded_within_window"] = bool(delta_days >= 0 and delta_days <= Decimal(int(args.bond_window_days)))
                else:
                    row["first_bond_after_inflow_block"] = 0
                    row["first_bond_after_inflow_time"] = ""
                    row["bond_after_inflow_days"] = ""
                    row["bonded_within_window"] = False

    # L1 outflows (best-effort): top-N recipients by inbound + all selected recipients
    # that are Arbitrum delegators (to ensure overlap rows carry outflow context).
    outflow_top_n = max(0, int(args.recipient_outflow_top_n))
    outflow_addr_set: set[str] = set()
    if outflow_top_n:
        for r in rows[:outflow_top_n]:
            outflow_addr_set.add(str(r["address"]))
    for r in rows:
        if r.get("is_arbitrum_delegator"):
            outflow_addr_set.add(str(r["address"]))
    outflow_rows = [r for r in rows if str(r["address"]) in outflow_addr_set]

    exchange_topic2 = [_pad_topic_address(a) for a in exchange_wallets]
    bridge_topic2 = [_pad_topic_address(a) for a in bridge_addrs]
    livepeer_contract_topic2 = [_pad_topic_address(a) for a in livepeer_contract_addrs]

    for idx, r in enumerate(outflow_rows, start=1):
        addr = r["address"]
        from_topic = _pad_topic_address(addr)

        exch_logs: List[Dict[str, Any]] = []
        bridge_logs: List[Dict[str, Any]] = []
        lp_logs: List[Dict[str, Any]] = []
        if exchange_topic2:
            exch_logs = _get_logs_range(
                eth,
                address=LPT_TOKEN_L1,
                topics=[TOPIC0_TRANSFER, from_topic, exchange_topic2],
                from_block=l1_from_block,
                to_block=l1_to_block,
            )
        if bridge_topic2:
            bridge_logs = _get_logs_range(
                eth,
                address=LPT_TOKEN_L1,
                topics=[TOPIC0_TRANSFER, from_topic, bridge_topic2],
                from_block=l1_from_block,
                to_block=l1_to_block,
            )
        if livepeer_contract_topic2:
            lp_logs = _get_logs_range(
                eth,
                address=LPT_TOKEN_L1,
                topics=[TOPIC0_TRANSFER, from_topic, livepeer_contract_topic2],
                from_block=l1_from_block,
                to_block=l1_to_block,
            )

        first_inbound_block = int(r.get("first_inbound_block") or 0)

        def _sum_after(logs: List[Dict[str, Any]]) -> Tuple[int, int]:
            total = 0
            count = 0
            for log in logs:
                try:
                    bn = int(str(log.get("blockNumber") or "0x0"), 16)
                except Exception:
                    continue
                if first_inbound_block and bn < first_inbound_block:
                    continue
                try:
                    total += int(str(log.get("data") or "0x0"), 16)
                    count += 1
                except Exception:
                    continue
            return total, count

        out_ex_wei, out_ex_n = _sum_after(exch_logs)
        out_br_wei, out_br_n = _sum_after(bridge_logs)
        out_lp_wei, out_lp_n = _sum_after(lp_logs)

        r["l1_outflow_to_exchanges_lpt"] = str(_wei_to_lpt(out_ex_wei))
        r["l1_outflow_to_exchanges_txs"] = int(out_ex_n)
        r["l1_outflow_to_bridges_lpt"] = str(_wei_to_lpt(out_br_wei))
        r["l1_outflow_to_bridges_txs"] = int(out_br_n)
        r["l1_outflow_to_livepeer_contracts_lpt"] = str(_wei_to_lpt(out_lp_wei))
        r["l1_outflow_to_livepeer_contracts_txs"] = int(out_lp_n)

        if idx % 20 == 0 or idx == len(outflow_rows):
            print(f"outflow classification: {idx}/{len(outflow_rows)} recipients …")

    total_inbound_lpt = sum((_wei_to_lpt(r.inbound_wei) for r in recipients.values()), Decimal(0))
    selected_inbound_lpt = sum((Decimal(str(r["exchange_inbound_lpt"])) for r in rows), Decimal(0))

    selected_delegators = [r for r in rows if r.get("is_arbitrum_delegator")]
    selected_delegators_inbound = sum((Decimal(str(r["exchange_inbound_lpt"])) for r in selected_delegators), Decimal(0))
    bonded_within = [r for r in selected_delegators if r.get("bonded_within_window")]
    bonded_within_inbound = sum((Decimal(str(r["exchange_inbound_lpt"])) for r in bonded_within), Decimal(0))

    labeled_outflows_lpt_by_category = {k: str(_wei_to_lpt(v)) for k, v in sorted(labeled_outflows_wei_by_category.items())}
    outflows_lpt_by_exchange_group = {k: str(_wei_to_lpt(v)) for k, v in sorted(outflows_wei_by_exchange_group.items())}

    out_json = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "ethereum_rpc": str(args.eth_rpc),
        "arbitrum_rpc": str(args.arb_rpc),
        "l1_window": {"from_block": int(l1_from_block), "to_block": int(l1_to_block)},
        "arb_window": {"from_block": int(arb_from_block), "to_block": int(arb_to_block)},
        "parameters": {
            "min_inbound_lpt": str(args.min_inbound_lpt),
            "max_recipients": int(args.max_recipients),
            "bond_window_days": int(args.bond_window_days),
            "recipient_outflow_top_n": int(args.recipient_outflow_top_n),
        },
        "labels": {
            "exchange_wallets": len(exchange_wallets),
            "bridge_addresses": len(bridge_addrs),
            "livepeer_contract_addresses": len(livepeer_contract_addrs),
        },
        "exchange_wallets_scanned": [
            {"address": a, "exchange": _label_exchange(labels, a), "name": _label_name(labels, a)} for a in exchange_wallets
        ],
        "labeled_destination_outflows_lpt_by_category": labeled_outflows_lpt_by_category,
        "exchange_outflows_lpt_by_exchange": outflows_lpt_by_exchange_group,
        "scan_totals": {
            "transfer_logs_matched": int(total_logs),
            "unique_unlabeled_recipients": int(len(recipients)),
            "total_unlabeled_recipient_inbound_lpt": str(total_inbound_lpt),
        },
        "selection_totals": {
            "selected_recipients": int(len(rows)),
            "selected_inbound_lpt": str(selected_inbound_lpt),
            "selected_delegators": int(len(selected_delegators)),
            "selected_delegators_inbound_lpt": str(selected_delegators_inbound),
            "bonded_within_window": int(len(bonded_within)),
            "bonded_within_window_inbound_lpt": str(bonded_within_inbound),
        },
        "recipients": rows,
    }

    _write_json(args.out_json, out_json)

    lines: List[str] = []
    lines.append("---")
    lines.append('title: "Buy pressure proxies (exchange outflows → bonders)"')
    lines.append(
        'description: "On-chain proxies for buy-side demand: labeled exchange outflows on L1 and whether recipients bond on Arbitrum."'
    )
    lines.append('sidebar_label: "Buy-side proxies"')
    lines.append("---")
    lines.append("")
    lines.append("# Buy pressure proxies (exchange outflows → bonders)")
    lines.append("")
    lines.append("Most LPT buying happens off-chain (CEX order books), so on-chain we use **proxies**:")
    lines.append("")
    lines.append("- L1 LPT transfers **from labeled exchange wallets** → recipient wallets (exchange outflows).")
    lines.append("- Whether those recipients **bond on Arbitrum**, and how soon after the first exchange inflow.")
    lines.append("- Best-effort overlap with **cashout-heavy** wallets (sell-pressure proxies).")
    lines.append("")
    lines.append("This is not proof of buyers or hedges; treat it as a reproducible signal to combine with other packs.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at']}`")
    lines.append(f"- Ethereum RPC: `{out_json['ethereum_rpc']}`")
    lines.append(f"- Arbitrum RPC: `{out_json['arbitrum_rpc']}`")
    lines.append(f"- L1 window: `{l1_from_block}` → `{l1_to_block}`")
    lines.append(f"- Arbitrum window (Bond scan): `{arb_from_block}` → `{arb_to_block}`")
    lines.append(f"- Labeled exchange wallets scanned: **{len(exchange_wallets)}**")
    lines.append(f"- Unique unlabeled recipients (any size): **{len(recipients):,}**")
    lines.append(f"- Total unlabeled recipient inbound: **{_format_lpt(total_inbound_lpt)} LPT**")
    lines.append("")
    lines.append(f"- Selected recipients (≥ {args.min_inbound_lpt} LPT): **{len(rows):,}**")
    lines.append(f"- Selected inbound total: **{_format_lpt(selected_inbound_lpt)} LPT**")
    lines.append(f"- Selected recipients in Arbitrum delegator set: **{len(selected_delegators):,}**")
    lines.append(f"- Bonded within {int(args.bond_window_days)}d of first exchange inflow: **{len(bonded_within):,}**")
    if selected_inbound_lpt > 0:
        share = (selected_delegators_inbound / selected_inbound_lpt) if selected_inbound_lpt > 0 else Decimal(0)
        lines.append(f"- Selected delegator inbound total: **{_format_lpt(selected_delegators_inbound)} LPT** ({float(share) * 100:.2f}%)")
        share2 = (bonded_within_inbound / selected_inbound_lpt) if selected_inbound_lpt > 0 else Decimal(0)
        lines.append(
            f"- Bonded-within-window inbound total: **{_format_lpt(bonded_within_inbound)} LPT** ({float(share2) * 100:.2f}%)"
        )
    lines.append("")

    lines.append("## Top recipients (selected)")
    lines.append("")
    lines.append(
        "Columns: inbound from labeled exchanges on L1, whether the address is known as an Arbitrum delegator, and (best-effort) whether it bonded soon after the first inflow."
    )
    lines.append("")
    lines.append("| Rank | Recipient | Inbound (LPT) | Txs | First inflow | Arbitrum delegator | Bond ≤ window | Bonded now (LPT) | Cashout fp |")
    lines.append("|---:|---|---:|---:|---:|:---:|:---:|---:|---:|")

    for r in rows[:50]:
        inbound = Decimal(str(r["exchange_inbound_lpt"]))
        first_iso = str(r["first_inbound_time"])
        is_del = "yes" if r.get("is_arbitrum_delegator") else ""
        bond_soon = "yes" if r.get("bonded_within_window") else ""
        bonded_now = Decimal(str(r.get("bonded_now_lpt") or "0"))
        cashout_rank = int(r.get("cashout_fingerprint_rank") or 0)
        cashout = f"#{cashout_rank}" if cashout_rank > 0 else ""
        lines.append(
            f"| {int(r['rank'])} | `{r['address']}` | {_format_lpt(inbound)} | {int(r['inbound_txs'])} | {first_iso[:10]} | {is_del} | {bond_soon} | {_format_lpt(bonded_now)} | {cashout} |"
        )

    lines.append("")
    if selected_delegators:
        lines.append("## Delegator overlap (selected)")
        lines.append("")
        lines.append("The selected recipients that overlap with the Arbitrum delegator set are rare and skew toward cashout-heavy wallets.")
        lines.append("")
        lines.append("| Rank | Delegator | Inbound (LPT) | First inflow | Bond after inflow (d) | To Livepeer L1 contracts (LPT) | To labeled exchanges (LPT) | Cashout fp |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|")
        for r in selected_delegators[:25]:
            inbound = Decimal(str(r["exchange_inbound_lpt"]))
            first_iso = str(r["first_inbound_time"])
            bond_days = str(r.get("bond_after_inflow_days") or "")
            lp_out = Decimal(str(r.get("l1_outflow_to_livepeer_contracts_lpt") or "0"))
            ex_out = Decimal(str(r.get("l1_outflow_to_exchanges_lpt") or "0"))
            cashout_rank = int(r.get("cashout_fingerprint_rank") or 0)
            cashout = f"#{cashout_rank}" if cashout_rank > 0 else ""
            lines.append(
                f"| {int(r['rank'])} | `{r['address']}` | {_format_lpt(inbound)} | {first_iso[:10]} | {bond_days[:8]} | {_format_lpt(lp_out)} | {_format_lpt(ex_out)} | {cashout} |"
            )
        lines.append("")
    lines.append("## Notes + limitations")
    lines.append("")
    lines.append("- “Exchange” coverage is label-set based; many exchange wallets are unlabeled.")
    lines.append("- Exchange outflows include internal wallet management as well as customer withdrawals; we exclude labeled destinations from the candidate set.")
    lines.append("- Seeing an exchange outflow followed by a bond is suggestive, but does not prove that the inflow funded the bond (bridging and wallet reuse can vary).")
    lines.append("- Recipient outflows are computed only for the top-N selected recipients and only to labeled exchanges/bridges (best-effort).")
    lines.append("")
    lines.append(f"Raw output: see `{args.out_json}`.")

    _write_text(args.out_md, "\n".join(lines) + "\n")

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
