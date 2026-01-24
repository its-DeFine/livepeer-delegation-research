#!/usr/bin/env python3
"""
The Graph (GRT) — delegation withdrawals → labeled exchange routing (on-chain only).

Goal
----
Produce an on-chain evidence pack comparable in spirit to Livepeer's extraction timing traces:

- detect delegation withdrawals from The Graph staking system (StakeDelegatedWithdrawn),
- then check whether the withdrawing delegator routes GRT into a *labeled* exchange endpoint
  within a tight window (default: 7 days), either:
  - direct: delegator → exchange, or
  - second hop: delegator → intermediate → exchange.

This does NOT prove "selling" (exchanges can custody), but it is a stronger behavioral proxy
than "withdraw happened".

Scope
-----
We focus on the Delegator path (not Indexer stake withdrawals), because it is closer to
Livepeer's delegator dynamics.

We intentionally keep labels conservative:
- uses this repo's `data/labels.json` exchange entries (small curated set)
- results are therefore a lower bound (unlabeled exchanges and unlabeled deposit addresses
  are not counted unless they sweep into a labeled endpoint)

Outputs
-------
- research/thegraph-delegation-withdrawal-routing.json
- research/thegraph-delegation-withdrawal-routing.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

ETHEREUM_RPC_DEFAULT = "https://ethereum.publicnode.com"

# The Graph mainnet contracts
THEGRAPH_STAKING_MAINNET = "0xF55041E37E12cD407ad00CE2910B8269B01263b9"
GRT_TOKEN_MAINNET = "0xc944e90c64b2c07662a292be6244bdf05cda44a7"

# cast sig-event "StakeDelegatedWithdrawn(address,address,uint256)"
TOPIC0_STAKE_DELEGATED_WITHDRAWN = "0x1b2e7737e043c5cf1b587ceb4daeb7ae00148b9bda8f79f1093eead08f141952"

# ERC20 Transfer(address,address,uint256)
TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

GRT_DECIMALS = 18
GRT_SCALE = Decimal(10) ** GRT_DECIMALS

# Function selectors
# cast sig "thawingPeriod()"
SEL_THAWING_PERIOD = "0xcdc747dd"
# cast sig "delegationUnbondingPeriod()"
SEL_DELEGATION_UNBONDING_PERIOD = "0xb6846e47"


class RpcError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/thegraph-withdraw-routing"):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self.user_agent = user_agent
        self._id = 0

    def call(self, method: str, params: list) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        body = json.dumps(payload).encode("utf-8")
        req = Request(self.rpc_url, data=body, headers={"content-type": "application/json", "user-agent": self.user_agent}, method="POST")
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
                    "remote end closed",
                    "remote disconnected",
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
            "response size exceeded",
            "block range too wide",
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
        if max_splits <= 0 or from_block >= to_block or not _is_chunkable_logs_error(str(e)):
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


def _get_logs_chunked(
    client: RpcClient,
    *,
    address: str,
    topics: list,
    from_block: int,
    to_block: int,
    chunk_size: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    cur = int(from_block)
    end = int(to_block)
    step = max(1, int(chunk_size))
    while cur <= end:
        chunk_to = min(end, cur + step - 1)
        out.extend(
            _get_logs_range(
                client,
                address=address,
                topics=topics,
                from_block=cur,
                to_block=chunk_to,
            )
        )
        print(f"logs: {address} {cur:,}..{chunk_to:,} (+{len(out):,} total)")
        cur = chunk_to + 1
    return out


def _hex_to_int(x: str) -> int:
    s = str(x or "").strip()
    if s.startswith("0x"):
        return int(s, 16)
    if s == "":
        return 0
    return int(s)


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _topic_to_address(topic: str) -> str:
    t = str(topic).lower()
    if not t.startswith("0x") or len(t) != 66:
        raise ValueError(f"invalid topic (address expected): {topic}")
    return "0x" + t[-40:]


def _pad_topic_address(addr: str) -> str:
    a = _normalize_address(addr)
    return "0x" + ("0" * 24) + a[2:]


def _wei_to_grt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / GRT_SCALE


def _format_grt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _eth_block_number(client: RpcClient) -> int:
    return _hex_to_int(_rpc_with_retries(client, "eth_blockNumber", []))


def _eth_call_int(client: RpcClient, *, to_addr: str, data: str, block_tag: str = "latest") -> int:
    res = _rpc_with_retries(client, "eth_call", [{"to": to_addr, "data": data}, block_tag])
    return _hex_to_int(res)


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


def _parse_decimal(s: str) -> Decimal:
    return Decimal(str(s).strip())


@dataclass(frozen=True)
class WithdrawalEvent:
    block_number: int
    tx_hash: str
    indexer: str
    delegator: str
    tokens_wei: int


@dataclass(frozen=True)
class ExchangeTransfer:
    block_number: int
    tx_hash: str
    to_addr: str
    amount_wei: int


@dataclass(frozen=True)
class OutgoingTransfer:
    block_number: int
    tx_hash: str
    to_addr: str
    amount_wei: int


def _eth_get_code(client: RpcClient, addr: str, *, block_tag: str = "latest") -> str:
    return str(_rpc_with_retries(client, "eth_getCode", [_normalize_address(addr), block_tag]) or "")


def _is_contract_address(client: RpcClient, addr: str, code_cache: Dict[str, bool]) -> bool:
    a = _normalize_address(addr)
    if a in code_cache:
        return bool(code_cache[a])
    code = _eth_get_code(client, a)
    is_contract = isinstance(code, str) and code not in ("", "0x", "0x0")
    code_cache[a] = is_contract
    return is_contract


def _scan_outgoing_transfers(
    client: RpcClient,
    *,
    from_addr: str,
    from_block: int,
    to_block: int,
    chunk_size: int,
) -> List[OutgoingTransfer]:
    logs = _get_logs_chunked(
        client,
        address=GRT_TOKEN_MAINNET,
        topics=[TOPIC0_TRANSFER, _pad_topic_address(from_addr)],
        from_block=int(from_block),
        to_block=int(to_block),
        chunk_size=int(chunk_size),
    )
    out: List[OutgoingTransfer] = []
    for log in logs:
        t = log.get("topics") or []
        if len(t) < 3:
            continue
        bn = int(str(log.get("blockNumber") or "0x0"), 16)
        if bn <= 0:
            continue
        txh = str(log.get("transactionHash") or "").lower()
        to_addr = _topic_to_address(t[2])
        amount_wei = _hex_to_int(str(log.get("data") or "0x0"))
        out.append(OutgoingTransfer(block_number=bn, tx_hash=txh, to_addr=to_addr, amount_wei=int(amount_wei)))
    out.sort(key=lambda x: (x.block_number, x.tx_hash))
    return out


def _scan_exchange_transfers_from(
    client: RpcClient,
    *,
    from_addr: str,
    from_block: int,
    to_block: int,
    exchange_topics: List[str],
    chunk_size: int,
) -> List[ExchangeTransfer]:
    logs = _get_logs_chunked(
        client,
        address=GRT_TOKEN_MAINNET,
        topics=[TOPIC0_TRANSFER, _pad_topic_address(from_addr), exchange_topics],
        from_block=int(from_block),
        to_block=int(to_block),
        chunk_size=int(chunk_size),
    )
    out: List[ExchangeTransfer] = []
    for log in logs:
        t = log.get("topics") or []
        if len(t) < 3:
            continue
        bn = int(str(log.get("blockNumber") or "0x0"), 16)
        if bn <= 0:
            continue
        txh = str(log.get("transactionHash") or "").lower()
        to_addr = _topic_to_address(t[2])
        amount_wei = _hex_to_int(str(log.get("data") or "0x0"))
        out.append(ExchangeTransfer(block_number=bn, tx_hash=txh, to_addr=to_addr, amount_wei=int(amount_wei)))
    out.sort(key=lambda x: (x.block_number, x.tx_hash))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eth-rpc", default=os.environ.get("ETH_RPC_URL") or ETHEREUM_RPC_DEFAULT)
    parser.add_argument("--days", type=int, default=180, help="How many days back to scan (approx; uses 7200 blocks/day).")
    parser.add_argument("--blocks-per-day", type=int, default=7200)
    parser.add_argument("--window-days", type=int, default=7, help="Post-withdraw routing window (days, approx).")
    parser.add_argument("--top-n", type=int, default=50, help="Analyze exchange routing for top-N delegators by withdrawn GRT.")
    # Public RPCs commonly cap eth_getLogs ranges (e.g., 50k). Keep the default conservative
    # to avoid pathological recursive splitting and frequent disconnects.
    parser.add_argument("--log-chunk-size", type=int, default=50_000, help="Block chunk size for eth_getLogs scans.")
    parser.add_argument(
        "--include-second-hop",
        action="store_true",
        help="Also check delegator → intermediate → exchange routing (lower bound; see report notes).",
    )
    parser.add_argument("--max-first-hops-per-withdrawal", type=int, default=6, help="Second hop: max first-hop transfers to consider per withdrawal.")
    parser.add_argument("--min-first-hop-grt", type=_parse_decimal, default=Decimal("1000"), help="Second hop: minimum first-hop transfer amount (GRT).")
    parser.add_argument(
        "--min-first-hop-fraction",
        type=_parse_decimal,
        default=Decimal("0.02"),
        help="Second hop: minimum first-hop transfer fraction of withdrawal amount (0..1). Threshold uses max(min-grt, fraction*withdraw).",
    )
    parser.add_argument(
        "--classify-intermediates",
        action="store_true",
        help="Second hop: call eth_getCode for intermediates in matched traces (EOA vs contract).",
    )
    parser.add_argument(
        "--classify-first-hop-dests",
        action="store_true",
        help="First-hop breakdown: call eth_getCode for first-hop destinations (EOA vs contract).",
    )
    parser.add_argument(
        "--include-third-hop",
        action="store_true",
        help="Also check delegator → intermediate → intermediate → exchange routing (lower bound; can be slower).",
    )
    parser.add_argument("--max-second-hops-per-first-hop", type=int, default=4, help="Third hop: max hop-2 transfers to consider per first-hop intermediate.")
    parser.add_argument("--min-second-hop-grt", type=_parse_decimal, default=Decimal("1000"), help="Third hop: minimum hop-2 transfer amount (GRT).")
    parser.add_argument(
        "--min-second-hop-fraction-of-first-hop",
        type=_parse_decimal,
        default=Decimal("0.50"),
        help="Third hop: minimum hop-2 transfer fraction of first-hop amount (0..1). Threshold uses max(min-grt, fraction*first-hop).",
    )
    parser.add_argument("--labels-json", default="data/labels.json")
    parser.add_argument("--out-json", default="research/thegraph-delegation-withdrawal-routing.json")
    parser.add_argument("--out-md", default="research/thegraph-delegation-withdrawal-routing.md")
    args = parser.parse_args()

    include_third_hop = bool(args.include_third_hop)
    include_second_hop = bool(args.include_second_hop) or include_third_hop
    classify_first_hop_dests = bool(args.classify_first_hop_dests)

    eth = RpcClient(str(args.eth_rpc), user_agent="livepeer-delegation-research/thegraph-withdraw-routing")

    latest_block = _eth_block_number(eth)
    from_block = max(0, latest_block - int(args.days) * int(args.blocks_per_day))
    to_block = int(latest_block)
    window_blocks = int(args.window_days) * int(args.blocks_per_day)

    thawing_period_blocks = _eth_call_int(eth, to_addr=THEGRAPH_STAKING_MAINNET, data=SEL_THAWING_PERIOD)
    delegation_unbonding_epochs = _eth_call_int(eth, to_addr=THEGRAPH_STAKING_MAINNET, data=SEL_DELEGATION_UNBONDING_PERIOD)

    labels = _load_json(str(args.labels_json))
    exchange_labels: Dict[str, Dict[str, Any]] = {
        _normalize_address(a): v
        for a, v in (labels or {}).items()
        if isinstance(v, dict) and v.get("category") == "exchange"
    }
    labeled_non_exchange_addrs: set[str] = set()
    if isinstance(labels, dict):
        for addr, meta in labels.items():
            if not isinstance(addr, str) or not isinstance(meta, dict):
                continue
            cat = meta.get("category")
            if isinstance(cat, str) and cat and cat != "exchange":
                try:
                    labeled_non_exchange_addrs.add(_normalize_address(addr))
                except ValueError:
                    continue
    exchange_addrs = sorted(exchange_labels.keys())
    exchange_topics = [_pad_topic_address(a) for a in exchange_addrs]

    # 1) Scan delegation withdrawals from Staking contract.
    withdraw_logs = _get_logs_chunked(
        eth,
        address=THEGRAPH_STAKING_MAINNET,
        topics=[[TOPIC0_STAKE_DELEGATED_WITHDRAWN]],
        from_block=from_block,
        to_block=to_block,
        chunk_size=int(args.log_chunk_size),
    )

    withdrawals: List[WithdrawalEvent] = []
    for log in withdraw_logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        block_number = int(str(log.get("blockNumber") or "0x0"), 16)
        if block_number <= 0:
            continue
        tx_hash = str(log.get("transactionHash") or "").lower()
        indexer = _topic_to_address(topics[1])
        delegator = _topic_to_address(topics[2])
        tokens_wei = _hex_to_int(str(log.get("data") or "0x0"))
        withdrawals.append(
            WithdrawalEvent(
                block_number=block_number,
                tx_hash=tx_hash,
                indexer=indexer,
                delegator=delegator,
                tokens_wei=int(tokens_wei),
            )
        )

    withdrawals.sort(key=lambda e: (e.block_number, e.tx_hash))

    total_withdraw_wei = sum(e.tokens_wei for e in withdrawals)
    unique_delegators = len({e.delegator for e in withdrawals})
    unique_indexers = len({e.indexer for e in withdrawals})

    by_delegator_wei: Dict[str, int] = defaultdict(int)
    by_delegator_events: Dict[str, int] = defaultdict(int)
    for e in withdrawals:
        by_delegator_wei[e.delegator] += int(e.tokens_wei)
        by_delegator_events[e.delegator] += 1

    top_delegators = sorted(by_delegator_wei.items(), key=lambda kv: kv[1], reverse=True)[: max(0, int(args.top_n))]
    top_delegator_set = {d for d, _ in top_delegators}

    # 2) For top-N delegators, query outgoing GRT transfers to labeled exchanges (small curated set).
    transfer_to_exchange_by_delegator: Dict[str, List[ExchangeTransfer]] = {}
    outgoing_transfers_by_delegator: Dict[str, List[OutgoingTransfer]] = {}

    for delegator, _amt in top_delegators:
        # Restrict scan range to just the delegator's withdrawal window(s) to keep this fast.
        delegator_withdrawals = [e for e in withdrawals if e.delegator == delegator]
        if not delegator_withdrawals:
            continue
        min_withdraw_block = min(e.block_number for e in delegator_withdrawals)
        max_withdraw_block = max(e.block_number for e in delegator_withdrawals)
        transfer_from_block = int(min_withdraw_block)
        transfer_to_block = int(max_withdraw_block + window_blocks)

        print(f"scan transfers: delegator={delegator} to exchanges (range {transfer_from_block:,}..{transfer_to_block:,})")
        transfer_to_exchange_by_delegator[delegator] = _scan_exchange_transfers_from(
            eth,
            from_addr=delegator,
            from_block=transfer_from_block,
            to_block=transfer_to_block,
            exchange_topics=exchange_topics,
            chunk_size=int(args.log_chunk_size),
        )

        if include_second_hop:
            print(f"scan outgoing: delegator={delegator} (range {transfer_from_block:,}..{transfer_to_block:,})")
            outgoing_transfers_by_delegator[delegator] = _scan_outgoing_transfers(
                eth,
                from_addr=delegator,
                from_block=transfer_from_block,
                to_block=transfer_to_block,
                chunk_size=int(args.log_chunk_size),
            )

    # 3) Match: for each withdrawal by a top delegator, look for exchange routing within the window.
    matched_direct_events: List[Dict[str, Any]] = []
    matched_second_hop_events: List[Dict[str, Any]] = []
    matched_third_hop_events: List[Dict[str, Any]] = []
    first_hop_category_by_withdraw_wei: Dict[str, int] = defaultdict(int)
    first_hop_category_by_firsthop_wei: Dict[str, int] = defaultdict(int)
    first_hop_category_by_events: Counter[str] = Counter()
    first_hop_category_examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    unmatched_events: int = 0
    matched_direct_tokens_wei = 0
    matched_second_hop_tokens_wei = 0
    matched_third_hop_tokens_wei = 0
    exchange_counter_direct: Counter[str] = Counter()
    exchange_counter_second_hop: Counter[str] = Counter()
    exchange_counter_third_hop: Counter[str] = Counter()
    second_hop_intermediate_counter: Counter[str] = Counter()
    third_hop_first_intermediate_counter: Counter[str] = Counter()
    third_hop_second_intermediate_counter: Counter[str] = Counter()

    exchange_transfers_from_cache: Dict[str, Dict[str, Any]] = {}
    outgoing_transfers_from_cache: Dict[str, Dict[str, Any]] = {}
    intermediate_code_cache: Dict[str, bool] = {}

    banned_intermediates = {
        _normalize_address(THEGRAPH_STAKING_MAINNET),
        _normalize_address(GRT_TOKEN_MAINNET),
        _normalize_address("0x0000000000000000000000000000000000000000"),
    }
    banned_intermediates.update(labeled_non_exchange_addrs)

    def _classify_first_hop_dest(to_addr: str) -> tuple[str, str | None, bool | None]:
        """Return (category, label, is_contract?) for a first-hop destination."""

        to_norm = _normalize_address(to_addr)
        if to_norm in exchange_labels:
            return "exchange", exchange_labels.get(to_norm, {}).get("name"), None
        if to_norm in labeled_non_exchange_addrs:
            # We keep this bucket coarse; specific label categories vary by protocol.
            cat = str(labels.get(to_norm, {}).get("category") or "labeled_non_exchange") if isinstance(labels, dict) else "labeled_non_exchange"
            name = str(labels.get(to_norm, {}).get("name") or "") if isinstance(labels, dict) else ""
            return f"labeled:{cat}", (name or None), None
        if classify_first_hop_dests:
            is_contract = _is_contract_address(eth, to_norm, intermediate_code_cache)
            return ("unknown_contract" if is_contract else "unknown_eoa"), None, bool(is_contract)
        return "unknown_unclassified", None, None

    def _record_first_hop(category: str, *, withdraw_wei: int, firsthop_wei: int | None, example: Dict[str, Any]) -> None:
        first_hop_category_by_events[category] += 1
        first_hop_category_by_withdraw_wei[category] += int(withdraw_wei)
        if firsthop_wei is not None:
            first_hop_category_by_firsthop_wei[category] += int(firsthop_wei)
        if len(first_hop_category_examples[category]) < 10:
            first_hop_category_examples[category].append(example)

    # Process chronologically so second-hop cache tends to extend forward only.
    for e in withdrawals:
        if e.delegator not in top_delegator_set:
            continue

        end_block = int(e.block_number + window_blocks)

        # First-hop breakdown: pick the earliest "meaningful" outgoing transfer (by amount threshold)
        # and classify its destination. This is a proxy for "where the withdrawal goes" under limited
        # on-chain observability (mixing with existing balances is possible).
        firsthop_category = "no_first_hop_meeting_threshold"
        firsthop_to: str | None = None
        firsthop_label: str | None = None
        firsthop_is_contract: bool | None = None
        firsthop_block: int | None = None
        firsthop_tx: str | None = None
        firsthop_amount_wei: int | None = None

        if include_second_hop:
            outgoing_all = outgoing_transfers_by_delegator.get(e.delegator) or []
            withdraw_grt = _wei_to_grt(e.tokens_wei)
            firsthop_threshold_grt = max(Decimal(args.min_first_hop_grt), Decimal(args.min_first_hop_fraction) * withdraw_grt)
            threshold_wei = int((firsthop_threshold_grt * GRT_SCALE).to_integral_value(rounding="ROUND_FLOOR"))
            for t in outgoing_all:
                if t.block_number <= e.block_number:
                    continue
                if t.block_number > end_block:
                    break
                to_norm = _normalize_address(t.to_addr)
                if to_norm in banned_intermediates:
                    continue
                if int(t.amount_wei) < threshold_wei:
                    continue
                firsthop_to = str(t.to_addr)
                firsthop_block = int(t.block_number)
                firsthop_tx = str(t.tx_hash)
                firsthop_amount_wei = int(t.amount_wei)
                firsthop_category, firsthop_label, firsthop_is_contract = _classify_first_hop_dest(firsthop_to)
                break

        _record_first_hop(
            firsthop_category,
            withdraw_wei=int(e.tokens_wei),
            firsthop_wei=firsthop_amount_wei,
            example={
                "withdraw_block": int(e.block_number),
                "withdraw_tx": str(e.tx_hash),
                "delegator": str(e.delegator),
                "withdraw_tokens_grt": str(_wei_to_grt(e.tokens_wei)),
                "first_hop_to": firsthop_to,
                "first_hop_label": firsthop_label,
                "first_hop_is_contract": firsthop_is_contract,
                "first_hop_block": firsthop_block,
                "first_hop_tx": firsthop_tx,
                "first_hop_amount_grt": str(_wei_to_grt(firsthop_amount_wei)) if firsthop_amount_wei is not None else None,
            },
        )

        # Direct: delegator -> labeled exchange
        transfers = transfer_to_exchange_by_delegator.get(e.delegator) or []
        direct_best: Optional[ExchangeTransfer] = None
        for t in transfers:
            if t.block_number <= e.block_number:
                continue
            if t.block_number > end_block:
                break
            direct_best = t
            break

        if direct_best is not None:
            matched_direct_tokens_wei += int(e.tokens_wei)
            exchange_counter_direct[direct_best.to_addr] += 1
            matched_direct_events.append(
                {
                    "withdraw_block": e.block_number,
                    "withdraw_tx": e.tx_hash,
                    "indexer": e.indexer,
                    "delegator": e.delegator,
                    "withdraw_tokens_grt": str(_wei_to_grt(e.tokens_wei)),
                    "exchange_to": direct_best.to_addr,
                    "exchange_label": exchange_labels.get(direct_best.to_addr, {}).get("name"),
                    "exchange_tx": direct_best.tx_hash,
                    "exchange_block": direct_best.block_number,
                    "blocks_after_withdraw": int(direct_best.block_number - e.block_number),
                    "exchange_transfer_amount_grt": str(_wei_to_grt(direct_best.amount_wei)),
                }
            )
            continue

        if not include_second_hop:
            unmatched_events += 1
            continue

        # Second hop: delegator -> intermediate -> labeled exchange
        outgoing = outgoing_transfers_by_delegator.get(e.delegator) or []
        min_first_hop_fraction = Decimal(args.min_first_hop_fraction)
        if min_first_hop_fraction < 0 or min_first_hop_fraction > 1:
            raise ValueError("--min-first-hop-fraction must be in [0,1]")
        min_first_hop_grt_wei = int(Decimal(args.min_first_hop_grt) * GRT_SCALE)
        min_first_hop_frac_wei = int(Decimal(int(e.tokens_wei)) * min_first_hop_fraction)
        min_first_hop_wei = max(int(min_first_hop_grt_wei), int(min_first_hop_frac_wei))

        delegator_norm = _normalize_address(e.delegator)
        candidates: List[OutgoingTransfer] = []
        for t in outgoing:
            if t.block_number <= e.block_number or t.block_number > end_block:
                continue
            to_norm = _normalize_address(t.to_addr)
            if to_norm == delegator_norm or to_norm in banned_intermediates:
                continue
            if to_norm in exchange_labels:
                # Would have been counted as a direct match if labeled.
                continue
            if int(t.amount_wei) < int(min_first_hop_wei):
                continue
            candidates.append(t)

        candidates.sort(key=lambda x: (-int(x.amount_wei), int(x.block_number), x.tx_hash))
        candidates = candidates[: max(0, int(args.max_first_hops_per_withdrawal))]

        best_second: Optional[Dict[str, Any]] = None
        best_third: Optional[Dict[str, Any]] = None

        min_second_hop_fraction = Decimal(args.min_second_hop_fraction_of_first_hop)
        if min_second_hop_fraction < 0 or min_second_hop_fraction > 1:
            raise ValueError("--min-second-hop-fraction-of-first-hop must be in [0,1]")
        min_second_hop_grt_wei = int(Decimal(args.min_second_hop_grt) * GRT_SCALE)

        for first in candidates:
            intermediate = _normalize_address(first.to_addr)
            if intermediate in banned_intermediates:
                continue

            query_from = int(first.block_number + 1)
            query_to = int(end_block)
            if query_from > query_to:
                continue

            intermediate_is_contract: Optional[bool] = None
            if include_third_hop or bool(args.classify_intermediates):
                intermediate_is_contract = _is_contract_address(eth, intermediate, intermediate_code_cache)

            # Second hop: intermediate -> exchange
            cache = exchange_transfers_from_cache.get(intermediate)
            if cache is None:
                print(f"scan second hop: intermediate={intermediate} → exchanges (range {query_from:,}..{query_to:,})")
                fetched = _scan_exchange_transfers_from(
                    eth,
                    from_addr=intermediate,
                    from_block=query_from,
                    to_block=query_to,
                    exchange_topics=exchange_topics,
                    chunk_size=int(args.log_chunk_size),
                )
                cache = {"from_block": int(query_from), "to_block": int(query_to), "transfers": fetched}
                exchange_transfers_from_cache[intermediate] = cache
            else:
                cached_from = int(cache["from_block"])
                cached_to = int(cache["to_block"])
                if query_from < cached_from:
                    print(f"scan second hop: intermediate={intermediate} → exchanges (extend {query_from:,}..{cached_from - 1:,})")
                    extra = _scan_exchange_transfers_from(
                        eth,
                        from_addr=intermediate,
                        from_block=int(query_from),
                        to_block=int(cached_from - 1),
                        exchange_topics=exchange_topics,
                        chunk_size=int(args.log_chunk_size),
                    )
                    cache["from_block"] = int(query_from)
                    cache["transfers"] = list(extra) + list(cache["transfers"])
                    cached_from = int(query_from)
                if query_to > cached_to:
                    print(f"scan second hop: intermediate={intermediate} → exchanges (extend {cached_to + 1:,}..{query_to:,})")
                    extra = _scan_exchange_transfers_from(
                        eth,
                        from_addr=intermediate,
                        from_block=int(cached_to + 1),
                        to_block=int(query_to),
                        exchange_topics=exchange_topics,
                        chunk_size=int(args.log_chunk_size),
                    )
                    cache["to_block"] = int(query_to)
                    cache["transfers"].extend(extra)

            transfers2 = [t for t in (cache["transfers"] or []) if int(t.block_number) >= query_from and int(t.block_number) <= query_to]
            if transfers2:
                second = transfers2[0]
                candidate_match: Dict[str, Any] = {
                    "withdraw_block": e.block_number,
                    "withdraw_tx": e.tx_hash,
                    "indexer": e.indexer,
                    "delegator": e.delegator,
                    "withdraw_tokens_grt": str(_wei_to_grt(e.tokens_wei)),
                    "first_hop_to": intermediate,
                    "first_hop_tx": first.tx_hash,
                    "first_hop_block": int(first.block_number),
                    "first_hop_amount_grt": str(_wei_to_grt(first.amount_wei)),
                    "second_hop_exchange_to": second.to_addr,
                    "second_hop_exchange_label": exchange_labels.get(second.to_addr, {}).get("name"),
                    "second_hop_tx": second.tx_hash,
                    "second_hop_block": int(second.block_number),
                    "blocks_after_withdraw_first_hop": int(first.block_number - e.block_number),
                    "blocks_after_first_hop": int(second.block_number - first.block_number),
                    "blocks_after_withdraw_total": int(second.block_number - e.block_number),
                    "second_hop_exchange_amount_grt": str(_wei_to_grt(second.amount_wei)),
                }
                if intermediate_is_contract is not None:
                    candidate_match["intermediate_is_contract"] = bool(intermediate_is_contract)

                if best_second is None:
                    best_second = candidate_match
                else:
                    if int(candidate_match["second_hop_block"]) < int(best_second["second_hop_block"]):
                        best_second = candidate_match
                    elif int(candidate_match["second_hop_block"]) == int(best_second["second_hop_block"]):
                        if Decimal(candidate_match["first_hop_amount_grt"]) > Decimal(best_second["first_hop_amount_grt"]):
                            best_second = candidate_match

                # Prefer minimal-hop matches; no need to explore third hop from this first-hop candidate.
                continue

            if not include_third_hop:
                continue

            # Third hop: intermediate -> intermediate2 -> exchange
            if intermediate_is_contract:
                # Avoid scanning very-high-volume contract addresses (DEX routers, etc.) for third hop.
                continue

            out_cache = outgoing_transfers_from_cache.get(intermediate)
            if out_cache is None:
                print(f"scan third hop: intermediate={intermediate} outgoing (range {query_from:,}..{query_to:,})")
                fetched_out = _scan_outgoing_transfers(
                    eth,
                    from_addr=intermediate,
                    from_block=query_from,
                    to_block=query_to,
                    chunk_size=int(args.log_chunk_size),
                )
                out_cache = {"from_block": int(query_from), "to_block": int(query_to), "transfers": fetched_out}
                outgoing_transfers_from_cache[intermediate] = out_cache
            else:
                cached_from = int(out_cache["from_block"])
                cached_to = int(out_cache["to_block"])
                if query_from < cached_from:
                    print(f"scan third hop: intermediate={intermediate} outgoing (extend {query_from:,}..{cached_from - 1:,})")
                    extra_out = _scan_outgoing_transfers(
                        eth,
                        from_addr=intermediate,
                        from_block=int(query_from),
                        to_block=int(cached_from - 1),
                        chunk_size=int(args.log_chunk_size),
                    )
                    out_cache["from_block"] = int(query_from)
                    out_cache["transfers"] = list(extra_out) + list(out_cache["transfers"])
                if query_to > cached_to:
                    print(f"scan third hop: intermediate={intermediate} outgoing (extend {cached_to + 1:,}..{query_to:,})")
                    extra_out = _scan_outgoing_transfers(
                        eth,
                        from_addr=intermediate,
                        from_block=int(cached_to + 1),
                        to_block=int(query_to),
                        chunk_size=int(args.log_chunk_size),
                    )
                    out_cache["to_block"] = int(query_to)
                    out_cache["transfers"].extend(extra_out)

            outgoing2 = [t for t in (out_cache["transfers"] or []) if int(t.block_number) >= query_from and int(t.block_number) <= query_to]
            if not outgoing2:
                continue

            min_second_hop_frac_wei = int(Decimal(int(first.amount_wei)) * min_second_hop_fraction)
            min_second_hop_wei = max(int(min_second_hop_grt_wei), int(min_second_hop_frac_wei))

            second_candidates: List[OutgoingTransfer] = []
            for t2 in outgoing2:
                to2 = _normalize_address(t2.to_addr)
                if to2 in banned_intermediates or to2 == delegator_norm or to2 == intermediate:
                    continue
                if to2 in exchange_labels:
                    # Would have been caught as second hop.
                    continue
                if int(t2.amount_wei) < int(min_second_hop_wei):
                    continue
                second_candidates.append(t2)

            second_candidates.sort(key=lambda x: (-int(x.amount_wei), int(x.block_number), x.tx_hash))
            second_candidates = second_candidates[: max(0, int(args.max_second_hops_per_first_hop))]

            for second_hop in second_candidates:
                intermediate2 = _normalize_address(second_hop.to_addr)
                if intermediate2 in banned_intermediates:
                    continue

                q2_from = int(second_hop.block_number + 1)
                q2_to = int(end_block)
                if q2_from > q2_to:
                    continue

                cache2 = exchange_transfers_from_cache.get(intermediate2)
                if cache2 is None:
                    print(f"scan third hop: intermediate2={intermediate2} → exchanges (range {q2_from:,}..{q2_to:,})")
                    fetched2 = _scan_exchange_transfers_from(
                        eth,
                        from_addr=intermediate2,
                        from_block=q2_from,
                        to_block=q2_to,
                        exchange_topics=exchange_topics,
                        chunk_size=int(args.log_chunk_size),
                    )
                    cache2 = {"from_block": int(q2_from), "to_block": int(q2_to), "transfers": fetched2}
                    exchange_transfers_from_cache[intermediate2] = cache2
                else:
                    cached_from = int(cache2["from_block"])
                    cached_to = int(cache2["to_block"])
                    if q2_from < cached_from:
                        print(f"scan third hop: intermediate2={intermediate2} → exchanges (extend {q2_from:,}..{cached_from - 1:,})")
                        extra2 = _scan_exchange_transfers_from(
                            eth,
                            from_addr=intermediate2,
                            from_block=int(q2_from),
                            to_block=int(cached_from - 1),
                            exchange_topics=exchange_topics,
                            chunk_size=int(args.log_chunk_size),
                        )
                        cache2["from_block"] = int(q2_from)
                        cache2["transfers"] = list(extra2) + list(cache2["transfers"])
                    if q2_to > cached_to:
                        print(f"scan third hop: intermediate2={intermediate2} → exchanges (extend {cached_to + 1:,}..{q2_to:,})")
                        extra2 = _scan_exchange_transfers_from(
                            eth,
                            from_addr=intermediate2,
                            from_block=int(cached_to + 1),
                            to_block=int(q2_to),
                            exchange_topics=exchange_topics,
                            chunk_size=int(args.log_chunk_size),
                        )
                        cache2["to_block"] = int(q2_to)
                        cache2["transfers"].extend(extra2)

                t3_list = [t for t in (cache2["transfers"] or []) if int(t.block_number) >= q2_from and int(t.block_number) <= q2_to]
                if not t3_list:
                    continue

                third = t3_list[0]

                intermediate2_is_contract: Optional[bool] = None
                if bool(args.classify_intermediates):
                    intermediate2_is_contract = _is_contract_address(eth, intermediate2, intermediate_code_cache)

                candidate_third: Dict[str, Any] = {
                    "withdraw_block": e.block_number,
                    "withdraw_tx": e.tx_hash,
                    "indexer": e.indexer,
                    "delegator": e.delegator,
                    "withdraw_tokens_grt": str(_wei_to_grt(e.tokens_wei)),
                    "first_hop_to": intermediate,
                    "first_hop_tx": first.tx_hash,
                    "first_hop_block": int(first.block_number),
                    "first_hop_amount_grt": str(_wei_to_grt(first.amount_wei)),
                    "second_hop_to": intermediate2,
                    "second_hop_tx": second_hop.tx_hash,
                    "second_hop_block": int(second_hop.block_number),
                    "second_hop_amount_grt": str(_wei_to_grt(second_hop.amount_wei)),
                    "third_hop_exchange_to": third.to_addr,
                    "third_hop_exchange_label": exchange_labels.get(third.to_addr, {}).get("name"),
                    "third_hop_tx": third.tx_hash,
                    "third_hop_block": int(third.block_number),
                    "blocks_after_withdraw_first_hop": int(first.block_number - e.block_number),
                    "blocks_after_first_hop": int(second_hop.block_number - first.block_number),
                    "blocks_after_second_hop": int(third.block_number - second_hop.block_number),
                    "blocks_after_withdraw_total": int(third.block_number - e.block_number),
                    "third_hop_exchange_amount_grt": str(_wei_to_grt(third.amount_wei)),
                }
                if bool(args.classify_intermediates):
                    if intermediate_is_contract is not None:
                        candidate_third["first_hop_intermediate_is_contract"] = bool(intermediate_is_contract)
                    if intermediate2_is_contract is not None:
                        candidate_third["second_hop_intermediate_is_contract"] = bool(intermediate2_is_contract)

                if best_third is None:
                    best_third = candidate_third
                else:
                    if int(candidate_third["third_hop_block"]) < int(best_third["third_hop_block"]):
                        best_third = candidate_third
                    elif int(candidate_third["third_hop_block"]) == int(best_third["third_hop_block"]):
                        if Decimal(candidate_third["second_hop_amount_grt"]) > Decimal(best_third["second_hop_amount_grt"]):
                            best_third = candidate_third

                # Keep searching: a different intermediate2 might reach an exchange earlier.

        if best_second is not None:
            matched_second_hop_tokens_wei += int(e.tokens_wei)
            exchange_counter_second_hop[str(best_second["second_hop_exchange_to"])] += 1
            second_hop_intermediate_counter[str(best_second["first_hop_to"])] += 1
            matched_second_hop_events.append(best_second)
            continue

        if include_third_hop and best_third is not None:
            matched_third_hop_tokens_wei += int(e.tokens_wei)
            exchange_counter_third_hop[str(best_third["third_hop_exchange_to"])] += 1
            third_hop_first_intermediate_counter[str(best_third["first_hop_to"])] += 1
            third_hop_second_intermediate_counter[str(best_third["second_hop_to"])] += 1
            matched_third_hop_events.append(best_third)
            continue

        unmatched_events += 1

    matched_total_tokens_wei = int(matched_direct_tokens_wei) + int(matched_second_hop_tokens_wei) + int(matched_third_hop_tokens_wei)
    exchange_counter_total: Counter[str] = Counter()
    exchange_counter_total.update(exchange_counter_direct)
    exchange_counter_total.update(exchange_counter_second_hop)
    exchange_counter_total.update(exchange_counter_third_hop)

    top_delegator_withdrawals = [e for e in withdrawals if e.delegator in top_delegator_set]
    top_delegator_withdraw_wei = sum(e.tokens_wei for e in top_delegator_withdrawals)

    out_json: Dict[str, Any] = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "eth_rpc": str(args.eth_rpc),
        "staking_contract": THEGRAPH_STAKING_MAINNET,
        "grt_token": GRT_TOKEN_MAINNET,
        "range": {"from_block": int(from_block), "to_block": int(to_block), "days_approx": int(args.days)},
        "params": {
            "thawing_period_blocks": int(thawing_period_blocks),
            "delegation_unbonding_period_epochs": int(delegation_unbonding_epochs),
        },
        "analysis": {
            "window_days": int(args.window_days),
            "window_blocks_approx": int(window_blocks),
            "labels_exchange_count": len(exchange_addrs),
            "top_n_delegators": int(args.top_n),
            "include_second_hop": bool(include_second_hop),
            "second_hop_max_first_hops_per_withdrawal": int(args.max_first_hops_per_withdrawal),
            "second_hop_min_first_hop_grt": str(Decimal(args.min_first_hop_grt)),
            "second_hop_min_first_hop_fraction": str(Decimal(args.min_first_hop_fraction)),
            "second_hop_classify_intermediates": bool(args.classify_intermediates),
            "first_hop_classify_destinations": bool(classify_first_hop_dests),
            "include_third_hop": bool(include_third_hop),
            "third_hop_max_second_hops_per_first_hop": int(args.max_second_hops_per_first_hop),
            "third_hop_min_second_hop_grt": str(Decimal(args.min_second_hop_grt)),
            "third_hop_min_second_hop_fraction_of_first_hop": str(Decimal(args.min_second_hop_fraction_of_first_hop)),
        },
        "totals": {
            "delegation_withdraw_events": len(withdrawals),
            "unique_delegators": int(unique_delegators),
            "unique_indexers": int(unique_indexers),
            "withdrawn_grt_total": str(_wei_to_grt(total_withdraw_wei)),
        },
        "top_delegators": [
            {
                "delegator": d,
                "withdrawn_grt": str(_wei_to_grt(amt)),
                "withdraw_events": int(by_delegator_events.get(d) or 0),
            }
            for d, amt in top_delegators
        ],
        "routing_results_top_delegators": {
            "withdraw_events_considered": len(top_delegator_withdrawals),
            "withdrawn_grt_considered": str(_wei_to_grt(top_delegator_withdraw_wei)),
            "first_hop_breakdown": {
                "method": "Earliest outgoing transfer >= max(min_first_hop_grt, min_first_hop_fraction*withdraw) within window; destination classified via labels and (optionally) eth_getCode.",
                "category_counts": dict(first_hop_category_by_events),
                "category_withdrawn_grt": {k: str(_wei_to_grt(v)) for k, v in first_hop_category_by_withdraw_wei.items()},
                "category_first_hop_grt": {k: str(_wei_to_grt(v)) for k, v in first_hop_category_by_firsthop_wei.items()},
                "examples": dict(first_hop_category_examples),
            },
            "matched_direct_to_exchange_within_window_events": len(matched_direct_events),
            "matched_direct_to_exchange_within_window_grt": str(_wei_to_grt(matched_direct_tokens_wei)),
            "matched_second_hop_to_exchange_within_window_events": len(matched_second_hop_events),
            "matched_second_hop_to_exchange_within_window_grt": str(_wei_to_grt(matched_second_hop_tokens_wei)),
            "matched_third_hop_to_exchange_within_window_events": len(matched_third_hop_events),
            "matched_third_hop_to_exchange_within_window_grt": str(_wei_to_grt(matched_third_hop_tokens_wei)),
            "matched_total_to_exchange_within_window_events": int(
                len(matched_direct_events) + len(matched_second_hop_events) + len(matched_third_hop_events)
            ),
            "matched_total_to_exchange_within_window_grt": str(_wei_to_grt(matched_total_tokens_wei)),
            "unmatched_events_in_top_delegators": int(unmatched_events),
            "exchange_transfer_count_by_to_direct": dict(exchange_counter_direct),
            "exchange_transfer_count_by_to_second_hop": dict(exchange_counter_second_hop),
            "exchange_transfer_count_by_to_third_hop": dict(exchange_counter_third_hop),
            "exchange_transfer_count_by_to_total": dict(exchange_counter_total),
            "unique_second_hop_intermediates": int(len(second_hop_intermediate_counter)),
            "unique_third_hop_first_intermediates": int(len(third_hop_first_intermediate_counter)),
            "unique_third_hop_second_intermediates": int(len(third_hop_second_intermediate_counter)),
        },
        "matched_examples_direct": sorted(matched_direct_events, key=lambda x: Decimal(x["withdraw_tokens_grt"]), reverse=True)[:25],
        "matched_examples_second_hop": sorted(matched_second_hop_events, key=lambda x: Decimal(x["withdraw_tokens_grt"]), reverse=True)[:25],
        "matched_examples_third_hop": sorted(matched_third_hop_events, key=lambda x: Decimal(x["withdraw_tokens_grt"]), reverse=True)[:25],
        "notes": [
            "This is a lower bound: it only counts transfers to a small curated set of labeled exchange addresses (data/labels.json).",
            "A transfer to an exchange does not prove a market sell, but is a strong proxy for off-protocol exit intent.",
            "Second hop routing (if enabled) is also a lower bound: it only detects intermediate addresses that sweep into a labeled exchange endpoint within the same window.",
            "Third hop routing (if enabled) is also a lower bound: it only detects intermediates that route into a labeled exchange endpoint within the same window.",
            "The Graph delegation unbonding is measured in epochs, while indexer thawing uses Ethereum blocks; this report focuses on withdrawal → (transfer) routing windows.",
        ],
    }

    _write_json(args.out_json, out_json)

    # Render markdown.
    lines: List[str] = []
    lines.append("---")
    lines.append('title: "The Graph: delegation withdrawals → exchange routing (on-chain)"')
    lines.append(
        'description: "Evidence pack: delegator withdrawals from The Graph staking contract and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."'
    )
    lines.append("---")
    lines.append("")
    lines.append("# The Graph: delegation withdrawals → exchange routing (on-chain)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- Ethereum RPC: `{out_json['eth_rpc']}`")
    lines.append(f"- Staking contract: `{THEGRAPH_STAKING_MAINNET}`")
    lines.append(f"- GRT token: `{GRT_TOKEN_MAINNET}`")
    lines.append("")
    lines.append("## Protocol parameters (on-chain)")
    lines.append("")
    lines.append(f"- `thawingPeriod()`: **{int(thawing_period_blocks):,} blocks** (Indexer unstake → withdraw delay)")
    lines.append(f"- `delegationUnbondingPeriod()`: **{int(delegation_unbonding_epochs)} epochs** (Delegator undelegate → withdraw delay)")
    lines.append("")
    lines.append("## Delegation withdrawals (events)")
    lines.append("")
    lines.append(f"- Range scanned: `{from_block:,}..{to_block:,}` (~{int(args.days)}d)")
    lines.append(f"- `StakeDelegatedWithdrawn` events: **{len(withdrawals):,}**")
    lines.append(f"- Unique delegators: **{unique_delegators:,}**")
    lines.append(f"- Total withdrawn (delegators): **{_format_grt(_wei_to_grt(total_withdraw_wei))} GRT**")
    lines.append("")
    lines.append("## Tight-window routing to labeled exchanges (top delegators)")
    lines.append("")
    lines.append(f"- Window: **{int(args.window_days)} days** (~{window_blocks:,} blocks)")
    lines.append(f"- Exchange label set size: **{len(exchange_addrs)}** addresses (`data/labels.json`)")
    lines.append(f"- Top delegators analyzed: **{len(top_delegators):,}**")
    lines.append("")
    lines.append(f"- Withdraw events considered (top delegators): **{len(top_delegator_withdrawals):,}**")
    lines.append(f"- Withdrawn amount considered: **{_format_grt(_wei_to_grt(top_delegator_withdraw_wei))} GRT**")
    lines.append(f"- Direct matched to labeled exchange within window (events): **{len(matched_direct_events):,}**")
    lines.append(f"- Direct matched amount (lower bound): **{_format_grt(_wei_to_grt(matched_direct_tokens_wei))} GRT**")
    if include_second_hop:
        lines.append(f"- Second hop matched to labeled exchange within window (events): **{len(matched_second_hop_events):,}**")
        lines.append(f"- Second hop matched amount (lower bound): **{_format_grt(_wei_to_grt(matched_second_hop_tokens_wei))} GRT**")
        if include_third_hop:
            lines.append(f"- Third hop matched to labeled exchange within window (events): **{len(matched_third_hop_events):,}**")
            lines.append(f"- Third hop matched amount (lower bound): **{_format_grt(_wei_to_grt(matched_third_hop_tokens_wei))} GRT**")
        lines.append(
            f"- Total matched (events): **{len(matched_direct_events) + len(matched_second_hop_events) + len(matched_third_hop_events):,}**"
        )
    lines.append(f"- Total matched amount (lower bound): **{_format_grt(_wei_to_grt(matched_total_tokens_wei))} GRT**")
    lines.append("")
    lines.append("## First hop destinations (top delegators; within window)")
    lines.append("")
    lines.append(
        "This categorizes the *first meaningful* outgoing GRT transfer after each withdrawal (>= max(min_first_hop_grt, min_first_hop_fraction*withdraw)) "
        "as a proxy for where the withdrawal goes. It can miss split flows or transfers below threshold."
    )
    lines.append("")
    fh = (out_json.get("routing_results_top_delegators") or {}).get("first_hop_breakdown") or {}
    fh_counts = fh.get("category_counts") or {}
    fh_withdrawn = fh.get("category_withdrawn_grt") or {}
    # Stable ordering for readability.
    for cat in sorted(fh_counts.keys()):
        cnt = fh_counts.get(cat)
        amt = fh_withdrawn.get(cat)
        lines.append(f"- {cat}: **{cnt:,}** events; **{_format_grt(Decimal(str(amt or '0')))} GRT** withdrawn")
    lines.append("")
    lines.append("Top exchange endpoints (by matched count):")
    lines.append("")
    for to_addr, cnt in exchange_counter_total.most_common(10):
        label = exchange_labels.get(to_addr, {}).get("name") or to_addr
        lines.append(f"- {label}: **{cnt:,}**")
    lines.append("")
    lines.append("## Example traces (largest matched withdrawals)")
    lines.append("")
    if out_json["matched_examples_direct"]:
        lines.append("Direct (delegator → exchange):")
        lines.append("")
        for ex in out_json["matched_examples_direct"][:10]:
            lines.append(
                f"- Delegator `{ex['delegator']}` withdrew {ex['withdraw_tokens_grt']} GRT (tx `{ex['withdraw_tx']}`) "
                f"→ sent to `{ex['exchange_to']}` ({ex.get('exchange_label')}) in {ex['blocks_after_withdraw']} blocks (tx `{ex['exchange_tx']}`)"
            )
        lines.append("")

    if include_second_hop and out_json["matched_examples_second_hop"]:
        lines.append("Second hop (delegator → intermediate → exchange):")
        lines.append("")
        for ex in out_json["matched_examples_second_hop"][:10]:
            extra = ""
            if "intermediate_is_contract" in ex:
                extra = " (contract)" if ex.get("intermediate_is_contract") else " (EOA)"
            lines.append(
                f"- Delegator `{ex['delegator']}` withdrew {ex['withdraw_tokens_grt']} GRT (tx `{ex['withdraw_tx']}`) "
                f"→ `{ex['first_hop_to']}`{extra} in {ex['blocks_after_withdraw_first_hop']} blocks (tx `{ex['first_hop_tx']}`) "
                f"→ `{ex['second_hop_exchange_to']}` ({ex.get('second_hop_exchange_label')}) in {ex['blocks_after_first_hop']} blocks (tx `{ex['second_hop_tx']}`)"
            )
        lines.append("")

    if include_third_hop and out_json["matched_examples_third_hop"]:
        lines.append("Third hop (delegator → intermediate → intermediate → exchange):")
        lines.append("")
        for ex in out_json["matched_examples_third_hop"][:10]:
            extra1 = ""
            extra2 = ""
            if "first_hop_intermediate_is_contract" in ex:
                extra1 = " (contract)" if ex.get("first_hop_intermediate_is_contract") else " (EOA)"
            if "second_hop_intermediate_is_contract" in ex:
                extra2 = " (contract)" if ex.get("second_hop_intermediate_is_contract") else " (EOA)"
            lines.append(
                f"- Delegator `{ex['delegator']}` withdrew {ex['withdraw_tokens_grt']} GRT (tx `{ex['withdraw_tx']}`) "
                f"→ `{ex['first_hop_to']}`{extra1} in {ex['blocks_after_withdraw_first_hop']} blocks (tx `{ex['first_hop_tx']}`) "
                f"→ `{ex['second_hop_to']}`{extra2} in {ex['blocks_after_first_hop']} blocks (tx `{ex['second_hop_tx']}`) "
                f"→ `{ex['third_hop_exchange_to']}` ({ex.get('third_hop_exchange_label')}) in {ex['blocks_after_second_hop']} blocks (tx `{ex['third_hop_tx']}`)"
            )
        lines.append("")
    lines.append("")
    lines.append("## Notes / limitations")
    lines.append("")
    lines.append("- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.")
    if include_second_hop:
        lines.append(
            "- Second hop routing is also a lower bound: it only detects intermediates that sweep into a labeled exchange endpoint within the same window."
        )
    if include_third_hop:
        lines.append(
            "- Third hop routing is also a lower bound: it only detects intermediates that route into a labeled exchange endpoint within the same window."
        )
    lines.append("- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.")
    lines.append("")
    lines.append(f"Raw output: see `{args.out_json}`.")

    _write_text(args.out_md, "\n".join(lines) + "\n")

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
