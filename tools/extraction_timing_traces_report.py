#!/usr/bin/env python3
"""
Livepeer — L2→L1 extraction timing traces (on-chain only).

Goal
----
Strengthen (or falsify) the "delta-neutral / systematic extraction" narrative using only
public on-chain signals.

We cannot see off-chain hedges (CEX loans / perps), but we *can* measure a harder-to-explain
behavioral pattern than "someone exited once":

  Arbitrum `WithdrawStake` → Arbitrum LPT bridge-out (burn) → L1 escrow release →
  tight-window routing into labeled exchange endpoints (often via a repeatable second-hop EOA)

This tool links those hops and outputs a reproducible evidence pack.

Inputs
------
- research/arbitrum-bridge-out-decode.json (burn txs decoded to L1 recipients + amounts)
- artifacts/delegator-bonded-amounts-cache.json (current bonded stake snapshot, Arbitrum)
- data/labels.json (small curated label set; best-effort exchange labels)

Outputs
-------
- research/extraction-timing-traces.json
- research/extraction-timing-traces.md

Notes / limitations
-------------------
- This is still not "proof of delta-neutral": it measures routing + timing, not the hedge.
- Labels are intentionally small; unlabeled EOAs can still be exchange deposits.
- Matching burn→L1 receipt is done by (recipient, amount, time ordering). It works well for
  canonical bridge-outs that unlock from the Livepeer L1 escrow.
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
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

ARBITRUM_RPC_DEFAULT = "https://arb1.arbitrum.io/rpc"
ETHEREUM_RPC_DEFAULT = "https://rpc.flashbots.net"

LIVEPEER_BONDING_MANAGER_ARB = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"
LPT_TOKEN_L1 = "0x58b6a8a3302369daec383334672404ee733ab239"

# cast sig-event "WithdrawStake(address,uint256,uint256)"
TOPIC0_WITHDRAW_STAKE = "0x1340f1a8f3d456a649e1a12071dfa15655e3d09252131d0f980c3b405cc8dd2e"

TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Livepeer L1 escrow (where canonical bridge-outs unlock from). Included in data/labels.json.
DEFAULT_L1_ESCROW = "0x6a23f4940bd5ba117da261f98aae51a8bffa210a"

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS


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
    def __init__(self, rpc_url: str, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/extraction-timing-traces"):
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


def _decode_words(data_hex: str, n: int) -> List[int]:
    if not data_hex.startswith("0x"):
        raise ValueError("data must be 0x-prefixed")
    hex_str = data_hex[2:]
    need = 64 * n
    if len(hex_str) < need:
        raise ValueError(f"data too short: need {need} hex chars, got {len(hex_str)}")
    return [int(hex_str[i : i + 64], 16) for i in range(0, need, 64)]


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


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
            "more than",
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
                "address": _normalize_address(address),
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
        return _get_logs_range(client, address=address, topics=topics, from_block=from_block, to_block=mid, max_splits=max_splits - 1) + _get_logs_range(
            client, address=address, topics=topics, from_block=mid + 1, to_block=to_block, max_splits=max_splits - 1
        )


def _block_timestamp(client: RpcClient, cache: Dict[int, int], block_number: int) -> int:
    if block_number in cache:
        return cache[block_number]
    block = _rpc_with_retries(client, "eth_getBlockByNumber", [hex(int(block_number)), False])
    if not isinstance(block, dict):
        raise RpcError(f"missing block {block_number}")
    ts = int(block["timestamp"], 16)
    cache[block_number] = ts
    return ts


def _latest_block(client: RpcClient) -> int:
    return int(str(_rpc_with_retries(client, "eth_blockNumber", []) or "0x0"), 16)


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
        if not text.endswith("\n"):
            f.write("\n")


def _median(xs: List[float]) -> Optional[float]:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2 == 1:
        return float(ys[mid])
    return float((ys[mid - 1] + ys[mid]) / 2.0)


@dataclass(frozen=True)
class BurnEvent:
    sender: str
    arb_tx_hash: str
    arb_block: int
    arb_ts: int
    l1_recipient: str
    amount_wei: int


@dataclass(frozen=True)
class WithdrawEvent:
    sender: str
    tx_hash: str
    block: int
    ts: int
    amount_wei: int


@dataclass(frozen=True)
class TransferEvent:
    from_addr: str
    to_addr: str
    tx_hash: str
    block: int
    ts: int
    amount_wei: int


def _decode_transfer_log(log: Dict[str, Any]) -> Tuple[str, str, int, int, str]:
    topics = [str(t).lower() for t in (log.get("topics") or [])]
    if len(topics) < 3 or topics[0] != TOPIC0_TRANSFER:
        raise ValueError("not a Transfer log")
    from_addr = _normalize_address("0x" + topics[1][-40:])
    to_addr = _normalize_address("0x" + topics[2][-40:])
    value_wei = int(str(log.get("data") or "0x0"), 16)
    block_number = int(str(log.get("blockNumber") or "0x0"), 16)
    tx_hash = str(log.get("transactionHash") or "")
    return from_addr, to_addr, value_wei, block_number, tx_hash


def _load_labels(path: str) -> Dict[str, Dict[str, str]]:
    if not path or not os.path.exists(path):
        return {}
    raw = json.load(open(path, "r", encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        try:
            addr = _normalize_address(k)
        except ValueError:
            continue
        out[addr] = {str(kk): str(vv) for kk, vv in v.items() if isinstance(kk, str) and isinstance(vv, str)}
    return out


def _label_name(labels: Dict[str, Dict[str, str]], addr: str) -> str:
    a = _normalize_address(addr)
    meta = labels.get(a) or {}
    name = str(meta.get("name") or "").strip()
    return name


def _label_category(labels: Dict[str, Dict[str, str]], addr: str) -> str:
    a = _normalize_address(addr)
    meta = labels.get(a) or {}
    return str(meta.get("category") or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arb-rpc", default=ARBITRUM_RPC_DEFAULT)
    parser.add_argument("--eth-rpc", default=ETHEREUM_RPC_DEFAULT)
    parser.add_argument("--bridge-decode-json", default="research/arbitrum-bridge-out-decode.json")
    parser.add_argument("--bonded-cache-json", default="artifacts/delegator-bonded-amounts-cache.json")
    parser.add_argument("--labels-json", default="data/labels.json")
    parser.add_argument("--bonding-manager", default=LIVEPEER_BONDING_MANAGER_ARB)
    parser.add_argument("--l1-token", default=LPT_TOKEN_L1)
    parser.add_argument("--l1-escrow", default=DEFAULT_L1_ESCROW)
    parser.add_argument("--l1-from-block", type=int, default=14_600_000)
    parser.add_argument("--l1-to-block", type=int, default=0, help="0 = latest")
    parser.add_argument("--l2-from-block", type=int, default=5_856_381)
    parser.add_argument("--l2-to-block", type=int, default=0, help="0 = latest (minus --l2-block-lag)")
    parser.add_argument("--l2-block-lag", type=int, default=200)
    parser.add_argument(
        "--withdraw-scan-buffer-blocks",
        type=int,
        default=5_000_000,
        help="When scanning WithdrawStake logs for a sender, use [minBurn-buffer, maxBurn] instead of full history.",
    )
    parser.add_argument("--max-senders", type=int, default=0, help="0 = all senders in bridge-decode-json")
    parser.add_argument("--withdraw-to-burn-hours", type=float, default=72.0)
    parser.add_argument("--burn-to-receipt-max-days", type=float, default=60.0)
    parser.add_argument("--receipt-to-firsthop-hours", type=float, default=72.0)
    parser.add_argument("--min-receipt-forward-ratio", type=float, default=0.90)
    parser.add_argument("--firsthop-to-exchange-hours", type=float, default=72.0)
    parser.add_argument("--out-json", default="research/extraction-timing-traces.json")
    parser.add_argument("--out-md", default="research/extraction-timing-traces.md")
    args = parser.parse_args()

    labels = _load_labels(str(args.labels_json))
    exchange_addrs = sorted([a for a in labels.keys() if _label_category(labels, a) == "exchange"])
    exchange_topics = [_pad_topic_address(a) for a in exchange_addrs]

    arb = RpcClient(str(args.arb_rpc), user_agent="livepeer-delegation-research/extraction-timing-traces/arb")
    eth = RpcClient(str(args.eth_rpc), user_agent="livepeer-delegation-research/extraction-timing-traces/eth")

    bridge = _load_json(str(args.bridge_decode_json))
    decoded = bridge.get("decoded_txs") or []
    if not isinstance(decoded, list) or not decoded:
        raise SystemExit(f"no decoded_txs in {args.bridge_decode_json}")

    # Determine L2 scan window.
    arb_latest = _latest_block(arb)
    arb_to_block = int(args.l2_to_block) or max(0, arb_latest - max(0, int(args.l2_block_lag)))
    arb_from_block = max(0, int(args.l2_from_block))
    if arb_from_block >= arb_to_block:
        raise SystemExit(f"l2 from_block {arb_from_block} >= to_block {arb_to_block}")

    l1_from_block = int(args.l1_from_block)
    l1_to_block = int(args.l1_to_block) or _latest_block(eth)
    if l1_from_block >= l1_to_block:
        raise SystemExit(f"l1 from_block {l1_from_block} >= to_block {l1_to_block}")

    bonded_cache = _load_json(str(args.bonded_cache_json))
    bonded_wei_by_addr = bonded_cache.get("bonded_amount_wei_by_address") or {}
    if not isinstance(bonded_wei_by_addr, dict):
        bonded_wei_by_addr = {}

    # Group burns by sender.
    burns_by_sender: Dict[str, List[BurnEvent]] = defaultdict(list)
    for row in decoded:
        if not isinstance(row, dict):
            continue
        try:
            sender = _normalize_address(row.get("from") or "")
            arb_tx = str(row.get("arb_tx_hash") or "")
            arb_block = int(row.get("arb_block") or 0)
            l1_to = _normalize_address(row.get("l1_to") or "")
            amount_wei = int(str(row.get("amount_wei") or "0"))
        except Exception:
            continue
        if not arb_tx or arb_block <= 0 or amount_wei <= 0:
            continue
        burns_by_sender[sender].append(
            BurnEvent(
                sender=sender,
                arb_tx_hash=arb_tx,
                arb_block=arb_block,
                arb_ts=0,
                l1_recipient=l1_to,
                amount_wei=amount_wei,
            )
        )

    if not burns_by_sender:
        raise SystemExit("no burns parsed from bridge decode json")

    # Sort senders by bridged total.
    sender_totals: List[Tuple[str, Decimal]] = []
    for sender, burns in burns_by_sender.items():
        total = sum((_wei_to_lpt(b.amount_wei) for b in burns), Decimal(0))
        sender_totals.append((sender, total))
    sender_totals.sort(key=lambda kv: kv[1], reverse=True)

    senders = [s for s, _t in sender_totals]
    if int(args.max_senders) > 0:
        senders = senders[: int(args.max_senders)]

    arb_block_ts_cache: Dict[int, int] = {}
    eth_block_ts_cache: Dict[int, int] = {}

    # Fill in Arbitrum timestamps for burns.
    for sender in senders:
        burns = burns_by_sender.get(sender) or []
        out: List[BurnEvent] = []
        for b in burns:
            ts = _block_timestamp(arb, arb_block_ts_cache, int(b.arb_block))
            out.append(
                BurnEvent(
                    sender=b.sender,
                    arb_tx_hash=b.arb_tx_hash,
                    arb_block=b.arb_block,
                    arb_ts=ts,
                    l1_recipient=b.l1_recipient,
                    amount_wei=b.amount_wei,
                )
            )
        out.sort(key=lambda x: (x.arb_ts, x.arb_block, x.arb_tx_hash))
        burns_by_sender[sender] = out

    # Pull withdraw events on Arbitrum for these senders.
    withdraws_by_sender: Dict[str, List[WithdrawEvent]] = {}
    for sender in senders:
        burns = burns_by_sender.get(sender) or []
        if burns:
            min_burn_block = min(b.arb_block for b in burns)
            max_burn_block = max(b.arb_block for b in burns)
            buffer_blocks = max(0, int(args.withdraw_scan_buffer_blocks))
            scan_from = max(arb_from_block, int(min_burn_block) - buffer_blocks)
            scan_to = min(arb_to_block, int(max_burn_block))
        else:
            scan_from = arb_from_block
            scan_to = arb_to_block

        topics = [TOPIC0_WITHDRAW_STAKE, _pad_topic_address(sender)]
        logs = _get_logs_range(
            arb,
            address=_normalize_address(args.bonding_manager),
            topics=topics,
            from_block=scan_from,
            to_block=scan_to,
        )

        evs: List[WithdrawEvent] = []
        for log in logs:
            try:
                block_number = int(str(log.get("blockNumber") or "0x0"), 16)
                if block_number <= 0:
                    continue
                ts = _block_timestamp(arb, arb_block_ts_cache, block_number)
                tx_hash = str(log.get("transactionHash") or "").lower()
                _lock_id, amount_wei, _withdraw_round = _decode_words(str(log.get("data") or "0x"), 3)
                if int(amount_wei) <= 0:
                    continue
                evs.append(
                    WithdrawEvent(
                        sender=sender,
                        tx_hash=tx_hash,
                        block=block_number,
                        ts=ts,
                        amount_wei=int(amount_wei),
                    )
                )
            except Exception:
                continue
        evs.sort(key=lambda x: (x.ts, x.block, x.tx_hash))
        withdraws_by_sender[sender] = evs

    # Pull L1 receipts (escrow -> recipient) for all unique recipients.
    all_recipients: List[str] = sorted({b.l1_recipient for s in senders for b in (burns_by_sender.get(s) or [])})
    escrow = _normalize_address(str(args.l1_escrow))
    l1_token = _normalize_address(str(args.l1_token))

    receipts_by_recipient: Dict[str, List[TransferEvent]] = {}

    for recipient in all_recipients:
        receipt_topics = [TOPIC0_TRANSFER, _pad_topic_address(escrow), _pad_topic_address(recipient)]
        receipt_logs = _get_logs_range(
            eth,
            address=l1_token,
            topics=receipt_topics,
            from_block=l1_from_block,
            to_block=l1_to_block,
        )
        receipts: List[TransferEvent] = []
        for log in receipt_logs:
            try:
                frm, to, value_wei, block_number, tx_hash = _decode_transfer_log(log)
                if frm != escrow or to != recipient or int(value_wei) <= 0:
                    continue
                ts = _block_timestamp(eth, eth_block_ts_cache, block_number)
                receipts.append(
                    TransferEvent(
                        from_addr=frm,
                        to_addr=to,
                        tx_hash=str(tx_hash).lower(),
                        block=block_number,
                        ts=ts,
                        amount_wei=int(value_wei),
                    )
                )
            except Exception:
                continue
        receipts.sort(key=lambda x: (x.ts, x.block, x.tx_hash))
        receipts_by_recipient[recipient] = receipts

    # L1 window scans can get expensive across years; we only need *tight windows*
    # after each receipt/forward. Use approximate block windows to keep RPC calls bounded.
    ASSUMED_L1_BLOCK_TIME_S = 12.0

    def approx_blocks_for_hours(hours: float) -> int:
        h = max(0.0, float(hours))
        # Add a small buffer for block time variance.
        return int((h * 3600.0) / ASSUMED_L1_BLOCK_TIME_S) + 256

    def get_outgoing_window(recipient: str, *, start_block: int, hours: float) -> List[TransferEvent]:
        end_block = min(l1_to_block, int(start_block) + approx_blocks_for_hours(hours))
        if start_block >= end_block:
            return []
        topics = [TOPIC0_TRANSFER, _pad_topic_address(recipient), None]
        logs = _get_logs_range(eth, address=l1_token, topics=topics, from_block=int(start_block), to_block=int(end_block))
        out: List[TransferEvent] = []
        for log in logs:
            try:
                frm, to, value_wei, block_number, tx_hash = _decode_transfer_log(log)
                if frm != recipient or int(value_wei) <= 0:
                    continue
                ts = _block_timestamp(eth, eth_block_ts_cache, block_number)
                out.append(
                    TransferEvent(
                        from_addr=frm,
                        to_addr=to,
                        tx_hash=str(tx_hash).lower(),
                        block=block_number,
                        ts=ts,
                        amount_wei=int(value_wei),
                    )
                )
            except Exception:
                continue
        out.sort(key=lambda x: (x.ts, x.block, x.tx_hash))
        return out

    def get_exchange_deposits_window(from_addr: str, *, start_block: int, hours: float) -> List[TransferEvent]:
        if not exchange_topics:
            return []
        end_block = min(l1_to_block, int(start_block) + approx_blocks_for_hours(hours))
        if start_block >= end_block:
            return []
        topics = [TOPIC0_TRANSFER, _pad_topic_address(from_addr), exchange_topics]
        logs = _get_logs_range(eth, address=l1_token, topics=topics, from_block=int(start_block), to_block=int(end_block))
        out: List[TransferEvent] = []
        for log in logs:
            try:
                frm, to, value_wei, block_number, tx_hash = _decode_transfer_log(log)
                if frm != _normalize_address(from_addr) or int(value_wei) <= 0:
                    continue
                ts = _block_timestamp(eth, eth_block_ts_cache, block_number)
                out.append(
                    TransferEvent(
                        from_addr=frm,
                        to_addr=to,
                        tx_hash=str(tx_hash).lower(),
                        block=block_number,
                        ts=ts,
                        amount_wei=int(value_wei),
                    )
                )
            except Exception:
                continue
        out.sort(key=lambda x: (x.ts, x.block, x.tx_hash))
        return out

    # Match burns -> receipts and then receipts -> exchange routing (via first hop).
    withdraw_to_burn_max_s = float(args.withdraw_to_burn_hours) * 3600.0
    burn_to_receipt_max_s = float(args.burn_to_receipt_max_days) * 86400.0
    receipt_to_firsthop_max_s = float(args.receipt_to_firsthop_hours) * 3600.0
    firsthop_to_exchange_max_s = float(args.firsthop_to_exchange_hours) * 3600.0
    min_forward_ratio = max(0.0, min(1.0, float(args.min_receipt_forward_ratio)))

    cycles: List[Dict[str, Any]] = []
    sender_summaries: List[Dict[str, Any]] = []

    used_receipt_keys: Dict[str, set[Tuple[int, str]]] = defaultdict(set)  # recipient -> {(block, tx_hash)}

    for sender in senders:
        burns = burns_by_sender.get(sender) or []
        withdraws = withdraws_by_sender.get(sender) or []

        # Find "still bonded now" (Arbitrum snapshot).
        bonded_now_wei = int(str(bonded_wei_by_addr.get(sender, 0) or 0))
        bonded_now_lpt = _wei_to_lpt(bonded_now_wei)

        matched_withdraw_deltas_h: List[float] = []
        matched_burn_to_receipt_d: List[float] = []
        matched_receipt_to_exchange_h: List[float] = []
        matched_receipt_to_firsthop_h: List[float] = []
        matched_firsthop_to_exchange_h: List[float] = []

        cycles_for_sender: List[Dict[str, Any]] = []

        for burn in burns:
            # L2: match nearest prior withdraw in time window.
            matched_withdraw: Optional[WithdrawEvent] = None
            for w in reversed(withdraws):
                if w.ts > burn.arb_ts:
                    continue
                dt_s = float(burn.arb_ts - w.ts)
                if dt_s <= withdraw_to_burn_max_s:
                    matched_withdraw = w
                    break
                # withdraws are sorted; once we cross the window, stop.
                if dt_s > withdraw_to_burn_max_s:
                    break

            # L1: match escrow receipt to burn by (recipient, amount, time ordering).
            recipient = burn.l1_recipient
            receipt_match: Optional[TransferEvent] = None
            for r in receipts_by_recipient.get(recipient) or []:
                key = (int(r.block), str(r.tx_hash))
                if key in used_receipt_keys[recipient]:
                    continue
                if int(r.amount_wei) != int(burn.amount_wei):
                    continue
                if r.ts < burn.arb_ts:
                    continue
                if float(r.ts - burn.arb_ts) > burn_to_receipt_max_s:
                    # receipts list is time-sorted; if this is already too late, future ones are too.
                    break
                receipt_match = r
                used_receipt_keys[recipient].add(key)
                break

            # L1: find first-hop forward from recipient after receipt.
            firsthop: Optional[TransferEvent] = None
            exchange_deposit: Optional[TransferEvent] = None
            exchange_via: str = "none"

            if receipt_match is not None:
                outs = get_outgoing_window(recipient, start_block=int(receipt_match.block), hours=float(args.receipt_to_firsthop_hours))
                window_end_ts = receipt_match.ts + int(receipt_to_firsthop_max_s)
                min_forward_wei = int(Decimal(receipt_match.amount_wei) * Decimal(str(min_forward_ratio)))
                cand: List[TransferEvent] = [
                    o for o in outs if o.ts >= receipt_match.ts and o.ts <= window_end_ts and int(o.amount_wei) >= min_forward_wei
                ]
                if cand:
                    # Prefer closest amount to the receipt amount, then earliest.
                    cand.sort(key=lambda o: (abs(int(o.amount_wei) - int(receipt_match.amount_wei)), o.ts, o.block))
                    firsthop = cand[0]

                    if _label_category(labels, firsthop.to_addr) == "exchange":
                        exchange_deposit = firsthop
                        exchange_via = "direct"
                    else:
                        deposits = get_exchange_deposits_window(
                            firsthop.to_addr, start_block=int(firsthop.block), hours=float(args.firsthop_to_exchange_hours)
                        )
                        for dep in deposits:
                            if dep.ts < firsthop.ts:
                                continue
                            exchange_deposit = dep
                            exchange_via = "second_hop"
                            break

            row: Dict[str, Any] = {
                "l2_sender": sender,
                "l2_sender_bonded_now_lpt": str(bonded_now_lpt),
                "l2_burn": {
                    "tx_hash": burn.arb_tx_hash,
                    "block": burn.arb_block,
                    "ts": burn.arb_ts,
                    "iso": _iso(burn.arb_ts),
                    "amount_lpt": str(_wei_to_lpt(burn.amount_wei)),
                    "l1_recipient": recipient,
                },
                "l2_withdraw": None,
                "l1_receipt": None,
                "l1_firsthop": None,
                "l1_exchange_deposit": None,
                "routing": {"exchange_via": exchange_via},
            }

            if matched_withdraw is not None:
                dt_h = float(burn.arb_ts - matched_withdraw.ts) / 3600.0
                matched_withdraw_deltas_h.append(dt_h)
                row["l2_withdraw"] = {
                    "tx_hash": matched_withdraw.tx_hash,
                    "block": matched_withdraw.block,
                    "ts": matched_withdraw.ts,
                    "iso": _iso(matched_withdraw.ts),
                    "amount_lpt": str(_wei_to_lpt(matched_withdraw.amount_wei)),
                    "withdraw_to_burn_hours": dt_h,
                }

            if receipt_match is not None:
                dt_d = float(receipt_match.ts - burn.arb_ts) / 86400.0
                matched_burn_to_receipt_d.append(dt_d)
                row["l1_receipt"] = {
                    "tx_hash": receipt_match.tx_hash,
                    "block": receipt_match.block,
                    "ts": receipt_match.ts,
                    "iso": _iso(receipt_match.ts),
                    "amount_lpt": str(_wei_to_lpt(receipt_match.amount_wei)),
                    "burn_to_receipt_days": dt_d,
                }

            if firsthop is not None and receipt_match is not None:
                dt_h = float(firsthop.ts - receipt_match.ts) / 3600.0
                matched_receipt_to_firsthop_h.append(dt_h)
                row["l1_firsthop"] = {
                    "tx_hash": firsthop.tx_hash,
                    "block": firsthop.block,
                    "ts": firsthop.ts,
                    "iso": _iso(firsthop.ts),
                    "to": firsthop.to_addr,
                    "to_label": _label_name(labels, firsthop.to_addr),
                    "to_category": _label_category(labels, firsthop.to_addr) or "unknown",
                    "amount_lpt": str(_wei_to_lpt(firsthop.amount_wei)),
                    "receipt_to_firsthop_hours": dt_h,
                }

            if exchange_deposit is not None:
                # receipt -> exchange
                if receipt_match is not None:
                    dt_h = float(exchange_deposit.ts - receipt_match.ts) / 3600.0
                    matched_receipt_to_exchange_h.append(dt_h)
                # firsthop -> exchange (for second-hop case)
                if firsthop is not None and exchange_via == "second_hop":
                    dt_h2 = float(exchange_deposit.ts - firsthop.ts) / 3600.0
                    matched_firsthop_to_exchange_h.append(dt_h2)

                row["l1_exchange_deposit"] = {
                    "tx_hash": exchange_deposit.tx_hash,
                    "block": exchange_deposit.block,
                    "ts": exchange_deposit.ts,
                    "iso": _iso(exchange_deposit.ts),
                    "from": exchange_deposit.from_addr,
                    "to": exchange_deposit.to_addr,
                    "to_label": _label_name(labels, exchange_deposit.to_addr),
                    "to_category": _label_category(labels, exchange_deposit.to_addr) or "unknown",
                    "amount_lpt": str(_wei_to_lpt(exchange_deposit.amount_wei)),
                }

            cycles.append(row)
            cycles_for_sender.append(row)

        # Aggregate sender metrics.
        burns_total_lpt = sum((_wei_to_lpt(b.amount_wei) for b in burns), Decimal(0))
        sender_summaries.append(
            {
                "sender": sender,
                "bonded_now_lpt": str(bonded_now_lpt),
                "burn_count": len(burns),
                "burn_total_lpt": str(burns_total_lpt),
                "withdraw_count": len(withdraws),
                "matched_withdraw_to_burn_count": sum(1 for c in cycles_for_sender if c.get("l2_withdraw") is not None),
                "matched_burn_to_receipt_count": sum(1 for c in cycles_for_sender if c.get("l1_receipt") is not None),
                "matched_receipt_to_exchange_count": sum(1 for c in cycles_for_sender if c.get("l1_exchange_deposit") is not None),
                "median_withdraw_to_burn_hours": _median(matched_withdraw_deltas_h),
                "median_burn_to_receipt_days": _median(matched_burn_to_receipt_d),
                "median_receipt_to_firsthop_hours": _median(matched_receipt_to_firsthop_h),
                "median_receipt_to_exchange_hours": _median(matched_receipt_to_exchange_h),
                "median_firsthop_to_exchange_hours": _median(matched_firsthop_to_exchange_h),
            }
        )

    # Summaries.
    sender_summaries.sort(key=lambda r: Decimal(str(r.get("burn_total_lpt") or "0")), reverse=True)
    totals = {
        "senders": len(senders),
        "burn_events": sum(int(r.get("burn_count") or 0) for r in sender_summaries),
        "withdraw_events": sum(int(r.get("withdraw_count") or 0) for r in sender_summaries),
        "matched_withdraw_to_burn": sum(int(r.get("matched_withdraw_to_burn_count") or 0) for r in sender_summaries),
        "matched_burn_to_receipt": sum(int(r.get("matched_burn_to_receipt_count") or 0) for r in sender_summaries),
        "matched_receipt_to_exchange": sum(int(r.get("matched_receipt_to_exchange_count") or 0) for r in sender_summaries),
    }

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "bridge_decode_json": str(args.bridge_decode_json),
            "bonded_cache_json": str(args.bonded_cache_json),
            "labels_json": str(args.labels_json),
        },
        "params": {
            "arb_rpc": str(args.arb_rpc),
            "eth_rpc": str(args.eth_rpc),
            "l1_token": l1_token,
            "l1_escrow": escrow,
            "l1_from_block": l1_from_block,
            "l1_to_block": l1_to_block,
            "l2_from_block": arb_from_block,
            "l2_to_block": arb_to_block,
            "withdraw_to_burn_hours": float(args.withdraw_to_burn_hours),
            "burn_to_receipt_max_days": float(args.burn_to_receipt_max_days),
            "receipt_to_firsthop_hours": float(args.receipt_to_firsthop_hours),
            "min_receipt_forward_ratio": float(args.min_receipt_forward_ratio),
            "firsthop_to_exchange_hours": float(args.firsthop_to_exchange_hours),
        },
        "labels": {
            "exchange_addresses": exchange_addrs,
        },
        "totals": totals,
        "senders": sender_summaries,
        "cycles": cycles,
    }

    _write_json(str(args.out_json), out_json)

    # Markdown evidence pack.
    lines: List[str] = []
    lines.append("---")
    lines.append('title: "Extraction timing traces (L2→L1→exchange)"')
    lines.append('description: "On-chain timing evidence: WithdrawStake → bridge-out → L1 escrow release → exchange routing (often via a repeatable second hop)."')
    lines.append('sidebar_label: "Timing traces"')
    lines.append("---")
    lines.append("")
    lines.append("# Extraction timing traces (L2→L1→exchange)")
    lines.append("")
    lines.append("This evidence pack attempts to strengthen (or falsify) the on-chain leg of the yield-extraction thesis by linking a tighter, repeatable sequence than a one-off exit:")
    lines.append("")
    lines.append("- Arbitrum `WithdrawStake` (liquid LPT leaves BondingManager)")
    lines.append("- Arbitrum bridge-out (LPT burn via gateway router)")
    lines.append("- Ethereum L1 escrow release (LPT transfer from the Livepeer L1 escrow)")
    lines.append("- Tight-window routing into **labeled** exchange endpoints (best-effort; often via a repeatable second-hop EOA)")
    lines.append("")
    lines.append("This is still **not proof of delta-neutral hedging** (the hedge is mostly off-chain). It is, however, a measurable “cashout routing + timing” fingerprint that is harder to explain as a single discretionary exit.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- Arbitrum RPC: `{args.arb_rpc}`")
    lines.append(f"- Ethereum RPC: `{args.eth_rpc}`")
    lines.append(f"- L1 token: `{l1_token}`")
    lines.append(f"- L1 escrow: `{escrow}`")
    lines.append(f"- L2 window: `{arb_from_block}` → `{arb_to_block}`")
    lines.append(f"- L1 window: `{l1_from_block}` → `{l1_to_block}`")
    lines.append("")
    lines.append(f"- Senders analyzed: **{totals['senders']}**")
    lines.append(f"- Burn (bridge-out) events: **{totals['burn_events']}**")
    lines.append(f"- Matched `WithdrawStake`→burn (≤ {args.withdraw_to_burn_hours}h): **{totals['matched_withdraw_to_burn']}**")
    lines.append(f"- Matched burn→L1 escrow receipt (≤ {args.burn_to_receipt_max_days}d): **{totals['matched_burn_to_receipt']}**")
    lines.append(f"- Matched L1 receipt→labeled exchange (≤ {args.receipt_to_firsthop_hours}h forward, then ≤ {args.firsthop_to_exchange_hours}h to exchange): **{totals['matched_receipt_to_exchange']}**")
    lines.append("")
    lines.append("## Sender table")
    lines.append("")
    lines.append("Columns: Arbitrum bonded stake **now** (snapshot), number of bridge-outs, and how many cycles can be followed all the way to a labeled exchange endpoint with tight timing windows.")
    lines.append("")
    lines.append("| Sender (L2) | Bonded now (LPT) | Burns | Matched withdraw→burn | Matched burn→L1 receipt | Matched receipt→exchange | Median burn→receipt (d) | Median receipt→exchange (h) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in sender_summaries:
        sender = str(s["sender"])
        bonded = Decimal(str(s.get("bonded_now_lpt") or "0"))
        burns = int(s.get("burn_count") or 0)
        m_wb = int(s.get("matched_withdraw_to_burn_count") or 0)
        m_br = int(s.get("matched_burn_to_receipt_count") or 0)
        m_rx = int(s.get("matched_receipt_to_exchange_count") or 0)
        med_br = s.get("median_burn_to_receipt_days")
        med_rx = s.get("median_receipt_to_exchange_hours")
        lines.append(
            f"| `{sender}` | {_format_lpt(bonded)} | {burns} | {m_wb} | {m_br} | {m_rx} | {med_br:.2f} | {med_rx:.2f} |"
            if isinstance(med_br, (int, float)) and isinstance(med_rx, (int, float))
            else f"| `{sender}` | {_format_lpt(bonded)} | {burns} | {m_wb} | {m_br} | {m_rx} |  |  |"
        )
    lines.append("")
    lines.append("## Notes + limitations")
    lines.append("")
    lines.append("- This report relies on the canonical Arbitrum bridge-out signature captured in `research/arbitrum-bridge-out-decode.json`.")
    lines.append("- “Exchange” routing is label-set based (best-effort). The absence of a labeled exchange does **not** imply the tokens weren’t sold.")
    lines.append("- Many flows route via one or more EOAs on L1 before an exchange deposit; this report only follows **one** intermediate hop.")
    lines.append("")
    lines.append("Raw output: see `research/extraction-timing-traces.json`.")

    _write_text(str(args.out_md), "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
