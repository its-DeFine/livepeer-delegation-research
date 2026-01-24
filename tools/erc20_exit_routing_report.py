#!/usr/bin/env python3
"""
Generic ERC20 "exit → exchange routing" evidence pack (EVM on-chain only).

This tool is a config-driven generalization of the Graph withdrawal routing pack:
- detect "exit" events (withdraw/redeem) from a specified contract + topic0,
- treat each exit event as a "token became liquid for <recipient>" moment,
- then check whether the recipient routes the ERC20 token into a *labeled* exchange endpoint
  within a post-exit window, using 0–3 hops (direct, 2-hop, 3-hop).

Like the other exchange-routing reports in this repo:
- The exchange label set is intentionally small (data/labels.json), so all shares are LOWER BOUNDS.
- Transfers into exchanges are not proof of selling, but a strong proxy for off-protocol exit intent.

Outputs
-------
- research/<slug>-exit-routing.json
- research/<slug>-exit-routing.md
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

# ERC20 Transfer(address,address,uint256)
TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class RpcError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/erc20-exit-routing"):
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
            "exceed maximum block range",
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
    chunk_size: int = 50_000,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    cur = int(from_block)
    while cur <= int(to_block):
        chunk_to = min(int(to_block), cur + int(chunk_size) - 1)
        try:
            logs = _get_logs_range(client, address=address, topics=topics, from_block=cur, to_block=chunk_to)
        except RpcError as e:
            # Some public RPCs fail non-deterministically on large ranges; split further by halving chunk size.
            if int(chunk_size) <= 5000:
                raise
            if not _is_chunkable_logs_error(str(e)):
                raise
            smaller = max(5000, int(chunk_size) // 2)
            return _get_logs_chunked(client, address=address, topics=topics, from_block=from_block, to_block=to_block, chunk_size=smaller)
        out.extend(logs or [])
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


def _word_from_data(data_hex: str, word_index: int) -> int:
    d = str(data_hex or "")
    if not d.startswith("0x"):
        raise ValueError("data must be 0x-prefixed hex")
    raw = d[2:]
    if len(raw) < 64 * (word_index + 1):
        raise ValueError(f"data too short for word[{word_index}]")
    start = 64 * word_index
    end = start + 64
    return int(raw[start:end], 16)


def _eth_block_number(client: RpcClient) -> int:
    return _hex_to_int(_rpc_with_retries(client, "eth_blockNumber", []))


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
class ExitEvent:
    block_number: int
    tx_hash: str
    recipient: str
    amount_wei: int


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
    token_addr: str,
    from_addr: str,
    from_block: int,
    to_block: int,
    chunk_size: int,
) -> List[OutgoingTransfer]:
    logs = _get_logs_chunked(
        client,
        address=_normalize_address(token_addr),
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
    token_addr: str,
    from_addr: str,
    from_block: int,
    to_block: int,
    exchange_topics: List[str],
    chunk_size: int,
) -> List[ExchangeTransfer]:
    logs = _get_logs_chunked(
        client,
        address=_normalize_address(token_addr),
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
    parser.add_argument("--protocol-name", required=True, help="Human name for the protocol (used in the report).")
    parser.add_argument("--slug", required=True, help="Output slug (e.g. curve-vecrv, frax-vefxs).")

    parser.add_argument("--token-symbol", required=True)
    parser.add_argument("--token-address", required=True)
    parser.add_argument("--token-decimals", type=int, default=18)

    parser.add_argument("--exit-contract", required=True, help="Contract that emits the exit event.")
    parser.add_argument("--exit-event-signature", required=True, help='Event signature, e.g. "Withdraw(address,uint256,uint256)".')
    parser.add_argument("--exit-topic0", required=True, help="Topic0 (keccak of signature). Use `cast sig-event` to compute.")
    parser.add_argument(
        "--recipient-topic-index",
        type=int,
        default=1,
        help="Which topics[i] holds the recipient address (excluding topic0). Example: 1 for topics[1].",
    )
    parser.add_argument(
        "--amount-data-index",
        type=int,
        default=0,
        help="Which 32-byte word in log.data is the amount (0-based). Example: 0 for first uint256.",
    )

    parser.add_argument("--days", type=int, default=90, help="How many days back to scan exit events (approx).")
    parser.add_argument("--blocks-per-day", type=int, default=7200)
    parser.add_argument("--window-days", type=int, default=30, help="Post-exit routing window (days, approx).")
    parser.add_argument("--top-n", type=int, default=50, help="Analyze exchange routing for top-N recipients by exit amount.")

    parser.add_argument("--log-chunk-size", type=int, default=50_000, help="Block chunk size for eth_getLogs scans.")
    parser.add_argument("--include-second-hop", action="store_true", help="Search second hop: recipient → intermediate → exchange.")
    parser.add_argument("--include-third-hop", action="store_true", help="Search third hop: recipient → inter1 → inter2 → exchange.")
    parser.add_argument("--classify-first-hop-dests", action="store_true", help="Classify first hop destination as EOA vs contract.")
    parser.add_argument("--classify-intermediates", action="store_true", help="For hop paths, classify intermediates as EOA vs contract.")

    parser.add_argument(
        "--max-first-hops-per-exit", type=int, default=6, help="Second hop: max first-hop transfers to consider per exit."
    )
    parser.add_argument("--min-first-hop-token", type=_parse_decimal, default=Decimal("1000"), help="Second hop: minimum first-hop transfer amount (token units).")
    parser.add_argument(
        "--min-first-hop-fraction",
        type=_parse_decimal,
        default=Decimal("0.02"),
        help="Second hop: minimum first-hop transfer as fraction of the exit amount.",
    )

    parser.add_argument(
        "--max-second-hops-per-first-hop",
        type=int,
        default=4,
        help="Third hop: max hop-2 transfers to consider per first-hop intermediate.",
    )
    parser.add_argument("--min-second-hop-token", type=_parse_decimal, default=Decimal("1000"), help="Third hop: minimum hop-2 transfer amount (token units).")
    parser.add_argument(
        "--min-second-hop-fraction-of-first-hop",
        type=_parse_decimal,
        default=Decimal("0.50"),
        help="Third hop: minimum hop-2 transfer as fraction of hop-1 transfer amount.",
    )

    parser.add_argument("--labels-json", default="data/labels.json")
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)

    args = parser.parse_args()

    token_addr = _normalize_address(args.token_address)
    exit_contract = _normalize_address(args.exit_contract)
    topic0_exit = str(args.exit_topic0).lower()
    if not topic0_exit.startswith("0x") or len(topic0_exit) != 66:
        raise ValueError("--exit-topic0 must be a 32-byte 0x-prefixed topic")

    if args.recipient_topic_index < 1:
        raise ValueError("--recipient-topic-index must be >= 1 (topics[0] is topic0)")
    if args.amount_data_index < 0:
        raise ValueError("--amount-data-index must be >= 0")

    out_json = args.out_json or f"research/{args.slug}-exit-routing.json"
    out_md = args.out_md or f"research/{args.slug}-exit-routing.md"

    scale = Decimal(10) ** int(args.token_decimals)

    def _wei_to_token(amount_wei: int | None) -> Decimal:
        if amount_wei is None:
            return Decimal(0)
        return Decimal(int(amount_wei)) / scale

    def _format_token(x: Decimal, *, places: int = 3) -> str:
        q = Decimal(10) ** -places
        return f"{x.quantize(q):,}"

    labels = _load_json(str(args.labels_json))
    if not isinstance(labels, dict):
        raise ValueError("labels json must be an object")

    exchange_labels: Dict[str, Dict[str, Any]] = {}
    labeled_non_exchange_addrs: set[str] = set()
    for addr, meta in labels.items():
        try:
            a = _normalize_address(addr)
        except Exception:
            continue
        if isinstance(meta, dict) and str(meta.get("category") or "") == "exchange":
            exchange_labels[a] = meta
        else:
            labeled_non_exchange_addrs.add(a)

    exchange_addrs = sorted(exchange_labels.keys())
    exchange_topics = [_pad_topic_address(a) for a in exchange_addrs]

    eth = RpcClient(str(args.eth_rpc))
    latest_block = _eth_block_number(eth)
    to_block = int(latest_block)
    from_block = max(0, to_block - int(args.days) * int(args.blocks_per_day))
    window_blocks = int(args.window_days) * int(args.blocks_per_day)

    print(f"scan exit events: contract={exit_contract} topic0={topic0_exit} range {from_block:,}..{to_block:,}")
    exit_logs = _get_logs_chunked(
        eth,
        address=exit_contract,
        topics=[topic0_exit],
        from_block=from_block,
        to_block=to_block,
        chunk_size=int(args.log_chunk_size),
    )

    exits: List[ExitEvent] = []
    exit_amount_by_recipient: Dict[str, int] = defaultdict(int)
    exit_events_by_recipient: Counter[str] = Counter()

    for log in exit_logs:
        topics = log.get("topics") or []
        if len(topics) <= int(args.recipient_topic_index):
            continue
        try:
            recipient = _topic_to_address(topics[int(args.recipient_topic_index)])
        except Exception:
            continue
        bn = int(str(log.get("blockNumber") or "0x0"), 16)
        if bn <= 0:
            continue
        txh = str(log.get("transactionHash") or "").lower()
        try:
            amount_wei = _word_from_data(str(log.get("data") or "0x0"), int(args.amount_data_index))
        except Exception:
            continue
        if int(amount_wei) <= 0:
            continue
        e = ExitEvent(block_number=bn, tx_hash=txh, recipient=recipient, amount_wei=int(amount_wei))
        exits.append(e)
        exit_amount_by_recipient[_normalize_address(recipient)] += int(amount_wei)
        exit_events_by_recipient[_normalize_address(recipient)] += 1

    exits.sort(key=lambda x: (x.block_number, x.tx_hash))

    unique_recipients = len(exit_amount_by_recipient)
    total_exit_wei = sum(int(e.amount_wei) for e in exits)
    print(f"exit events: {len(exits)}; unique recipients: {unique_recipients}; total exited: {_format_token(_wei_to_token(total_exit_wei))} {args.token_symbol}")

    top = sorted(exit_amount_by_recipient.items(), key=lambda kv: kv[1], reverse=True)[: max(0, int(args.top_n))]
    top_set = {a for a, _amt in top}

    top_rows: List[Dict[str, Any]] = []
    for a, amt_wei in top:
        top_rows.append(
            {
                "address": a,
                "exit_events": int(exit_events_by_recipient.get(a) or 0),
                "exit_amount": str(_wei_to_token(amt_wei)),
                "exit_amount_wei": int(amt_wei),
            }
        )

    considered_exits = [e for e in exits if _normalize_address(e.recipient) in top_set]
    considered_exit_wei = sum(int(e.amount_wei) for e in considered_exits)

    print(f"top recipients analyzed: {len(top_set)}; exit events considered: {len(considered_exits)}")

    # Pre-scan outgoing transfers for top recipients (once) to keep the per-exit loop fast.
    transfer_from_block = min((e.block_number for e in considered_exits), default=from_block)
    transfer_to_block = to_block

    transfer_to_exchange_by_recipient: Dict[str, List[ExchangeTransfer]] = {}
    outgoing_transfers_by_recipient: Dict[str, List[OutgoingTransfer]] = {}

    for addr_norm in sorted(top_set):
        print(f"scan transfers: recipient={addr_norm} to exchanges (range {transfer_from_block:,}..{transfer_to_block:,})")
        transfer_to_exchange_by_recipient[addr_norm] = _scan_exchange_transfers_from(
            eth,
            token_addr=token_addr,
            from_addr=addr_norm,
            from_block=transfer_from_block,
            to_block=transfer_to_block,
            exchange_topics=exchange_topics,
            chunk_size=int(args.log_chunk_size),
        )
        if args.include_second_hop or args.include_third_hop or args.classify_first_hop_dests:
            print(f"scan outgoing: recipient={addr_norm} (range {transfer_from_block:,}..{transfer_to_block:,})")
            outgoing_transfers_by_recipient[addr_norm] = _scan_outgoing_transfers(
                eth,
                token_addr=token_addr,
                from_addr=addr_norm,
                from_block=transfer_from_block,
                to_block=transfer_to_block,
                chunk_size=int(args.log_chunk_size),
            )

    banned_intermediates = {token_addr, exit_contract, _normalize_address("0x0000000000000000000000000000000000000000")}
    banned_intermediates.update(labeled_non_exchange_addrs)

    classify_first_hop_dests = bool(args.classify_first_hop_dests)
    intermediate_code_cache: Dict[str, bool] = {}

    first_hop_category_by_events: Counter[str] = Counter()
    first_hop_category_by_exit_wei: Dict[str, int] = defaultdict(int)
    first_hop_category_by_firsthop_wei: Dict[str, int] = defaultdict(int)
    first_hop_category_examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def _classify_first_hop_dest(to_addr: str) -> tuple[str, str | None, bool | None]:
        to_norm = _normalize_address(to_addr)
        if to_norm in exchange_labels:
            return "exchange", exchange_labels.get(to_norm, {}).get("name"), None
        if to_norm in labeled_non_exchange_addrs:
            cat = str(labels.get(to_norm, {}).get("category") or "labeled_non_exchange") if isinstance(labels, dict) else "labeled_non_exchange"
            name = str(labels.get(to_norm, {}).get("name") or "") if isinstance(labels, dict) else ""
            return f"labeled:{cat}", (name or None), None
        if classify_first_hop_dests:
            is_contract = _is_contract_address(eth, to_norm, intermediate_code_cache)
            return ("unknown_contract" if is_contract else "unknown_eoa"), None, bool(is_contract)
        return "unknown_unclassified", None, None

    def _record_first_hop(category: str, *, exit_wei: int, firsthop_wei: int | None, example: Dict[str, Any]) -> None:
        first_hop_category_by_events[category] += 1
        first_hop_category_by_exit_wei[category] += int(exit_wei)
        if firsthop_wei is not None:
            first_hop_category_by_firsthop_wei[category] += int(firsthop_wei)
        if len(first_hop_category_examples[category]) < 10:
            first_hop_category_examples[category].append(example)

    matched_direct_exit_wei = 0
    matched_second_exit_wei = 0
    matched_third_exit_wei = 0
    matched_direct_event_count = 0
    matched_second_event_count = 0
    matched_third_event_count = 0
    matched_direct_events: List[Dict[str, Any]] = []
    matched_second_events: List[Dict[str, Any]] = []
    matched_third_events: List[Dict[str, Any]] = []
    exchange_counter_direct: Counter[str] = Counter()
    exchange_counter_second: Counter[str] = Counter()
    exchange_counter_third: Counter[str] = Counter()

    exchange_transfers_from_cache: Dict[str, Dict[str, Any]] = {}
    outgoing_transfers_from_cache: Dict[str, Dict[str, Any]] = {}

    # Process chronologically so caches tend to extend forward only.
    for e in considered_exits:
        end_block = int(e.block_number + window_blocks)
        recipient_norm = _normalize_address(e.recipient)

        # First-hop breakdown (thresholded earliest outgoing transfer).
        firsthop_category = "no_first_hop_meeting_threshold"
        firsthop_to: str | None = None
        firsthop_label: str | None = None
        firsthop_is_contract: bool | None = None
        firsthop_block: int | None = None
        firsthop_tx: str | None = None
        firsthop_amount_wei: int | None = None

        outgoing_all = outgoing_transfers_by_recipient.get(recipient_norm) or []
        firsthop_threshold = max(Decimal(args.min_first_hop_token), Decimal(args.min_first_hop_fraction) * _wei_to_token(e.amount_wei))
        threshold_wei = int((firsthop_threshold * scale).to_integral_value(rounding="ROUND_FLOOR"))
        if outgoing_all and threshold_wei > 0:
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
            exit_wei=int(e.amount_wei),
            firsthop_wei=firsthop_amount_wei,
            example={
                "exit_block": int(e.block_number),
                "exit_tx": str(e.tx_hash),
                "recipient": str(e.recipient),
                "exit_amount": str(_wei_to_token(e.amount_wei)),
                "first_hop_to": firsthop_to,
                "first_hop_label": firsthop_label,
                "first_hop_is_contract": firsthop_is_contract,
                "first_hop_block": firsthop_block,
                "first_hop_tx": firsthop_tx,
                "first_hop_amount": str(_wei_to_token(firsthop_amount_wei)) if firsthop_amount_wei is not None else None,
            },
        )

        # Direct: recipient -> labeled exchange
        transfers = transfer_to_exchange_by_recipient.get(recipient_norm) or []
        direct_best: Optional[ExchangeTransfer] = None
        for t in transfers:
            if t.block_number <= e.block_number:
                continue
            if t.block_number > end_block:
                break
            direct_best = t
            break

        if direct_best is not None:
            matched_direct_exit_wei += int(e.amount_wei)
            matched_direct_event_count += 1
            exchange_counter_direct[_normalize_address(direct_best.to_addr)] += 1
            if len(matched_direct_events) < 25:
                matched_direct_events.append(
                    {
                        "exit_block": int(e.block_number),
                        "exit_tx": str(e.tx_hash),
                        "recipient": str(e.recipient),
                        "exit_amount": str(_wei_to_token(e.amount_wei)),
                        "exchange_to": str(direct_best.to_addr),
                        "exchange_label": exchange_labels.get(_normalize_address(direct_best.to_addr), {}).get("name"),
                        "exchange_tx": str(direct_best.tx_hash),
                        "exchange_block": int(direct_best.block_number),
                        "blocks_after_exit": int(direct_best.block_number - e.block_number),
                        "exchange_transfer_amount": str(_wei_to_token(direct_best.amount_wei)),
                    }
                )
            continue

        if not bool(args.include_second_hop) and not bool(args.include_third_hop):
            continue

        # Second hop: recipient -> intermediate -> labeled exchange
        min_first_hop_fraction = Decimal(args.min_first_hop_fraction)
        if min_first_hop_fraction < 0 or min_first_hop_fraction > 1:
            raise ValueError("--min-first-hop-fraction must be in [0,1]")

        min_first_hop_wei = max(
            int((Decimal(args.min_first_hop_token) * scale).to_integral_value(rounding="ROUND_FLOOR")),
            int((Decimal(int(e.amount_wei)) * min_first_hop_fraction).to_integral_value(rounding="ROUND_FLOOR")),
        )

        candidates: List[OutgoingTransfer] = []
        for t in outgoing_all:
            if t.block_number <= e.block_number or t.block_number > end_block:
                continue
            to_norm = _normalize_address(t.to_addr)
            if to_norm == recipient_norm or to_norm in banned_intermediates:
                continue
            if to_norm in exchange_labels:
                continue
            if int(t.amount_wei) < int(min_first_hop_wei):
                continue
            candidates.append(t)

        candidates.sort(key=lambda x: (-int(x.amount_wei), int(x.block_number), x.tx_hash))
        candidates = candidates[: max(0, int(args.max_first_hops_per_exit))]

        best_second: Optional[Dict[str, Any]] = None
        best_third: Optional[Dict[str, Any]] = None

        min_second_hop_fraction = Decimal(args.min_second_hop_fraction_of_first_hop)
        if min_second_hop_fraction < 0 or min_second_hop_fraction > 1:
            raise ValueError("--min-second-hop-fraction-of-first-hop must be in [0,1]")
        min_second_hop_wei_abs = int((Decimal(args.min_second_hop_token) * scale).to_integral_value(rounding="ROUND_FLOOR"))

        for first in candidates:
            intermediate = _normalize_address(first.to_addr)
            if intermediate in banned_intermediates:
                continue

            intermediate_is_contract: Optional[bool] = None
            if bool(args.classify_intermediates):
                intermediate_is_contract = _is_contract_address(eth, intermediate, intermediate_code_cache)

            query_from = int(first.block_number + 1)
            query_to = int(end_block)
            if query_from > query_to:
                continue

            cache = exchange_transfers_from_cache.get(intermediate)
            if cache is None:
                fetched = _scan_exchange_transfers_from(
                    eth,
                    token_addr=token_addr,
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
                    extra = _scan_exchange_transfers_from(
                        eth,
                        token_addr=token_addr,
                        from_addr=intermediate,
                        from_block=int(query_from),
                        to_block=int(cached_from - 1),
                        exchange_topics=exchange_topics,
                        chunk_size=int(args.log_chunk_size),
                    )
                    cache["from_block"] = int(query_from)
                    cache["transfers"] = list(extra) + list(cache["transfers"])
                if query_to > cached_to:
                    extra = _scan_exchange_transfers_from(
                        eth,
                        token_addr=token_addr,
                        from_addr=intermediate,
                        from_block=int(cached_to + 1),
                        to_block=int(query_to),
                        exchange_topics=exchange_topics,
                        chunk_size=int(args.log_chunk_size),
                    )
                    cache["to_block"] = int(query_to)
                    cache["transfers"].extend(extra)

            t2_list = [t for t in (cache["transfers"] or []) if int(t.block_number) >= query_from and int(t.block_number) <= query_to]
            if t2_list:
                second = t2_list[0]
                candidate_second: Dict[str, Any] = {
                    "exit_block": int(e.block_number),
                    "exit_tx": str(e.tx_hash),
                    "recipient": str(e.recipient),
                    "exit_amount": str(_wei_to_token(e.amount_wei)),
                    "first_hop_to": intermediate,
                    "first_hop_tx": str(first.tx_hash),
                    "first_hop_block": int(first.block_number),
                    "first_hop_amount": str(_wei_to_token(first.amount_wei)),
                    "second_hop_exchange_to": str(second.to_addr),
                    "second_hop_exchange_label": exchange_labels.get(_normalize_address(second.to_addr), {}).get("name"),
                    "second_hop_tx": str(second.tx_hash),
                    "second_hop_block": int(second.block_number),
                    "blocks_after_exit_first_hop": int(first.block_number - e.block_number),
                    "blocks_after_first_hop": int(second.block_number - first.block_number),
                    "blocks_after_exit_total": int(second.block_number - e.block_number),
                    "second_hop_exchange_amount": str(_wei_to_token(second.amount_wei)),
                }
                if bool(args.classify_intermediates) and intermediate_is_contract is not None:
                    candidate_second["first_hop_intermediate_is_contract"] = bool(intermediate_is_contract)

                if best_second is None:
                    best_second = candidate_second
                else:
                    if int(candidate_second["second_hop_block"]) < int(best_second["second_hop_block"]):
                        best_second = candidate_second
                    elif int(candidate_second["second_hop_block"]) == int(best_second["second_hop_block"]):
                        if Decimal(candidate_second["first_hop_amount"]) > Decimal(best_second["first_hop_amount"]):
                            best_second = candidate_second

                # Prefer minimal-hop match; no need to explore third hop for this first-hop candidate.
                continue

            if not bool(args.include_third_hop):
                continue

            # Third hop: recipient -> inter1 -> inter2 -> exchange
            if intermediate_is_contract:
                # Avoid scanning very-high-volume contract addresses (DEX routers, etc.) for third hop.
                continue

            out_cache = outgoing_transfers_from_cache.get(intermediate)
            if out_cache is None:
                fetched_out = _scan_outgoing_transfers(
                    eth,
                    token_addr=token_addr,
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
                    extra_out = _scan_outgoing_transfers(
                        eth,
                        token_addr=token_addr,
                        from_addr=intermediate,
                        from_block=int(query_from),
                        to_block=int(cached_from - 1),
                        chunk_size=int(args.log_chunk_size),
                    )
                    out_cache["from_block"] = int(query_from)
                    out_cache["transfers"] = list(extra_out) + list(out_cache["transfers"])
                if query_to > cached_to:
                    extra_out = _scan_outgoing_transfers(
                        eth,
                        token_addr=token_addr,
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

            min_second_hop_wei = max(int(min_second_hop_wei_abs), int(int(first.amount_wei) * min_second_hop_fraction))

            second_candidates: List[OutgoingTransfer] = []
            for t in outgoing2:
                to2 = _normalize_address(t.to_addr)
                if to2 in banned_intermediates or to2 == recipient_norm or to2 == intermediate:
                    continue
                if to2 in exchange_labels:
                    continue
                if int(t.amount_wei) < int(min_second_hop_wei):
                    continue
                second_candidates.append(t)

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
                    fetched2 = _scan_exchange_transfers_from(
                        eth,
                        token_addr=token_addr,
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
                        extra2 = _scan_exchange_transfers_from(
                            eth,
                            token_addr=token_addr,
                            from_addr=intermediate2,
                            from_block=int(q2_from),
                            to_block=int(cached_from - 1),
                            exchange_topics=exchange_topics,
                            chunk_size=int(args.log_chunk_size),
                        )
                        cache2["from_block"] = int(q2_from)
                        cache2["transfers"] = list(extra2) + list(cache2["transfers"])
                    if q2_to > cached_to:
                        extra2 = _scan_exchange_transfers_from(
                            eth,
                            token_addr=token_addr,
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
                    "exit_block": int(e.block_number),
                    "exit_tx": str(e.tx_hash),
                    "recipient": str(e.recipient),
                    "exit_amount": str(_wei_to_token(e.amount_wei)),
                    "first_hop_to": intermediate,
                    "first_hop_tx": str(first.tx_hash),
                    "first_hop_block": int(first.block_number),
                    "first_hop_amount": str(_wei_to_token(first.amount_wei)),
                    "second_hop_to": intermediate2,
                    "second_hop_tx": str(second_hop.tx_hash),
                    "second_hop_block": int(second_hop.block_number),
                    "second_hop_amount": str(_wei_to_token(second_hop.amount_wei)),
                    "third_hop_exchange_to": str(third.to_addr),
                    "third_hop_exchange_label": exchange_labels.get(_normalize_address(third.to_addr), {}).get("name"),
                    "third_hop_tx": str(third.tx_hash),
                    "third_hop_block": int(third.block_number),
                    "blocks_after_exit_first_hop": int(first.block_number - e.block_number),
                    "blocks_after_first_hop": int(second_hop.block_number - first.block_number),
                    "blocks_after_second_hop": int(third.block_number - second_hop.block_number),
                    "blocks_after_exit_total": int(third.block_number - e.block_number),
                    "third_hop_exchange_amount": str(_wei_to_token(third.amount_wei)),
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
                        if Decimal(candidate_third["second_hop_amount"]) > Decimal(best_third["second_hop_amount"]):
                            best_third = candidate_third

        if best_second is not None:
            matched_second_exit_wei += int(e.amount_wei)
            matched_second_event_count += 1
            exchange_counter_second[_normalize_address(str(best_second["second_hop_exchange_to"]))] += 1
            if len(matched_second_events) < 25:
                matched_second_events.append(best_second)
            continue

        if best_third is not None:
            matched_third_exit_wei += int(e.amount_wei)
            matched_third_event_count += 1
            exchange_counter_third[_normalize_address(str(best_third["third_hop_exchange_to"]))] += 1
            if len(matched_third_events) < 25:
                matched_third_events.append(best_third)

    matched_total_exit_wei = matched_direct_exit_wei + matched_second_exit_wei + matched_third_exit_wei
    matched_total_event_count = matched_direct_event_count + matched_second_event_count + matched_third_event_count

    first_hop_breakdown: dict[str, Any] | None = None
    if bool(args.classify_first_hop_dests) or bool(args.include_second_hop) or bool(args.include_third_hop):
        cat_counts = dict(first_hop_category_by_events)
        cat_withdrawn = {k: str(_wei_to_token(v)) for k, v in first_hop_category_by_exit_wei.items()}
        cat_firsthop = {k: str(_wei_to_token(v)) for k, v in first_hop_category_by_firsthop_wei.items()}
        first_hop_breakdown = {
            "method": "Earliest outgoing transfer >= max(min_first_hop_token, min_first_hop_fraction*exit) within window; destination classified via labels and (optionally) eth_getCode.",
            "category_counts": cat_counts,
            "category_exit_amount": cat_withdrawn,
            "category_first_hop_amount": cat_firsthop,
            "examples": first_hop_category_examples,
        }

    generated_at = datetime.now(timezone.utc).isoformat()

    out: Dict[str, Any] = {
        "generated_at_utc": generated_at,
        "eth_rpc": str(args.eth_rpc),
        "protocol": {"name": str(args.protocol_name), "chain": "ethereum"},
        "token": {"symbol": str(args.token_symbol), "address": token_addr, "decimals": int(args.token_decimals)},
        "exit_event": {
            "contract": exit_contract,
            "signature": str(args.exit_event_signature),
            "topic0": topic0_exit,
            "recipient_topic_index": int(args.recipient_topic_index),
            "amount_data_index": int(args.amount_data_index),
        },
        "range": {"from_block": int(from_block), "to_block": int(to_block), "days_approx": int(args.days)},
        "analysis": {
            "window_days": int(args.window_days),
            "blocks_per_day": int(args.blocks_per_day),
            "top_n": int(args.top_n),
            "labels_json": str(args.labels_json),
            "labels_exchange_count": int(len(exchange_addrs)),
            "include_second_hop": bool(args.include_second_hop),
            "include_third_hop": bool(args.include_third_hop),
            "classify_first_hop_dests": bool(args.classify_first_hop_dests),
            "classify_intermediates": bool(args.classify_intermediates),
            "thresholds": {
                "max_first_hops_per_exit": int(args.max_first_hops_per_exit),
                "min_first_hop_token": str(Decimal(args.min_first_hop_token)),
                "min_first_hop_fraction": str(Decimal(args.min_first_hop_fraction)),
                "max_second_hops_per_first_hop": int(args.max_second_hops_per_first_hop),
                "min_second_hop_token": str(Decimal(args.min_second_hop_token)),
                "min_second_hop_fraction_of_first_hop": str(Decimal(args.min_second_hop_fraction_of_first_hop)),
            },
        },
        "totals": {
            "exit_events_total": int(len(exits)),
            "unique_recipients": int(unique_recipients),
            "exit_amount_total": str(_wei_to_token(total_exit_wei)),
            "exit_amount_total_wei": int(total_exit_wei),
            "exit_events_considered_top_n": int(len(considered_exits)),
            "exit_amount_considered_top_n": str(_wei_to_token(considered_exit_wei)),
            "exit_amount_considered_top_n_wei": int(considered_exit_wei),
        },
        "top_recipients": top_rows,
        "routing_results_top_recipients": {
            "exit_events_considered": int(len(considered_exits)),
            "exit_amount_considered": str(_wei_to_token(considered_exit_wei)),
            "matched_direct_to_exchange_within_window_events": int(matched_direct_event_count),
            "matched_direct_to_exchange_within_window_amount": str(_wei_to_token(matched_direct_exit_wei)),
            "matched_second_hop_to_exchange_within_window_events": int(matched_second_event_count),
            "matched_second_hop_to_exchange_within_window_amount": str(_wei_to_token(matched_second_exit_wei)),
            "matched_third_hop_to_exchange_within_window_events": int(matched_third_event_count),
            "matched_third_hop_to_exchange_within_window_amount": str(_wei_to_token(matched_third_exit_wei)),
            "matched_total_to_exchange_within_window_events": int(matched_total_event_count),
            "matched_total_to_exchange_within_window_amount": str(_wei_to_token(matched_total_exit_wei)),
            "first_hop_breakdown": first_hop_breakdown,
            "top_exchange_endpoints_by_count": [
                {
                    "address": str(a),
                    "label": exchange_labels.get(a, {}).get("name"),
                    "count": int(c),
                }
                for a, c in (exchange_counter_direct + exchange_counter_second + exchange_counter_third).most_common(10)
            ],
        },
        "matched_examples_direct": matched_direct_events,
        "matched_examples_second_hop": matched_second_events,
        "matched_examples_third_hop": matched_third_events,
        "notes": [
            "Exchange routing is a LOWER BOUND: labels are incomplete and hop/window limits miss many paths.",
            "Matched amounts are summed by exit event amount (not the exchange transfer amount).",
        ],
    }

    _write_json(str(out_json), out)

    # Markdown
    lines: List[str] = []
    lines.append("---")
    lines.append(f'title: "{args.protocol_name}: exit → exchange routing (on-chain)"')
    lines.append(
        'description: "Evidence pack: on-chain exit events and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."'
    )
    lines.append("---")
    lines.append("")
    lines.append(f"# {args.protocol_name}: exit → exchange routing (on-chain)")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}`")
    lines.append(f"- Ethereum RPC: `{args.eth_rpc}`")
    lines.append(f"- Exit contract: `{exit_contract}`")
    lines.append(f"- Exit event: `{args.exit_event_signature}` (topic0 `{topic0_exit}`)")
    lines.append(f"- Token: `{token_addr}` ({args.token_symbol})")
    lines.append("")
    lines.append("## Exit events (observed)")
    lines.append("")
    lines.append(f"- Range scanned: `{from_block:,}..{to_block:,}` (~{int(args.days)}d)")
    lines.append(f"- Exit events: **{len(exits)}**")
    lines.append(f"- Unique recipients: **{unique_recipients}**")
    lines.append(f"- Total exited (events): **{_format_token(_wei_to_token(total_exit_wei))} {args.token_symbol}**")
    lines.append("")
    lines.append("## Tight-window routing to labeled exchanges (top recipients)")
    lines.append("")
    lines.append(f"- Window: **{int(args.window_days)} days** (~{window_blocks:,} blocks)")
    lines.append(f"- Exchange label set size: **{len(exchange_addrs)}** addresses (`{args.labels_json}`)")
    lines.append(f"- Top recipients analyzed: **{len(top_set)}**")
    lines.append("")
    lines.append(f"- Exit events considered (top recipients): **{len(considered_exits)}**")
    lines.append(f"- Exit amount considered: **{_format_token(_wei_to_token(considered_exit_wei))} {args.token_symbol}**")
    lines.append(f"- Direct matched within window (events): **{matched_direct_event_count}**")
    lines.append(f"- Direct matched amount (lower bound): **{_format_token(_wei_to_token(matched_direct_exit_wei))} {args.token_symbol}**")
    lines.append(f"- Second hop matched within window (events): **{matched_second_event_count}**")
    lines.append(f"- Second hop matched amount (lower bound): **{_format_token(_wei_to_token(matched_second_exit_wei))} {args.token_symbol}**")
    lines.append(f"- Third hop matched within window (events): **{matched_third_event_count}**")
    lines.append(f"- Third hop matched amount (lower bound): **{_format_token(_wei_to_token(matched_third_exit_wei))} {args.token_symbol}**")
    lines.append(f"- Total matched (events): **{matched_total_event_count}**")
    lines.append(f"- Total matched amount (lower bound): **{_format_token(_wei_to_token(matched_total_exit_wei))} {args.token_symbol}**")

    if first_hop_breakdown is not None:
        lines.append("")
        lines.append("## First hop destinations (top recipients; within window)")
        lines.append("")
        lines.append(
            "This categorizes the *first meaningful* outgoing token transfer after each exit (>= max(min_first_hop_token, min_first_hop_fraction*exit)) as a proxy for where the exit goes. It can miss split flows or transfers below threshold."
        )
        lines.append("")
        counts = first_hop_breakdown.get("category_counts") or {}
        amounts = first_hop_breakdown.get("category_exit_amount") or {}
        for k, v in sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0]))):
            lines.append(f"- {k}: **{int(v)}** events; **{_format_token(Decimal(str(amounts.get(k) or '0')))} {args.token_symbol}** exited")

    top_endpoints = out["routing_results_top_recipients"]["top_exchange_endpoints_by_count"]
    if isinstance(top_endpoints, list) and top_endpoints:
        lines.append("")
        lines.append("Top exchange endpoints (by matched count):")
        lines.append("")
        for row in top_endpoints:
            if not isinstance(row, dict):
                continue
            label = row.get("label") or row.get("address")
            c = int(row.get("count") or 0)
            lines.append(f"- {label}: **{c}**")

    lines.append("")
    lines.append("## Notes / limitations")
    lines.append("")
    lines.append("- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.")
    lines.append("- Hop routing is a lower bound: it only detects intermediates that sweep into labeled exchange endpoints within the same window.")
    lines.append("- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.")
    lines.append("")
    lines.append(f"Raw output: see `{out_json}`.")

    _write_text(str(out_md), "\n".join(lines) + "\n")

    print(f"wrote: {out_json}")
    print(f"wrote: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
