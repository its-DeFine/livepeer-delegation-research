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
ARBITRUM_RPC_DEFAULT = "https://arb1.arbitrum.io/rpc"

# Arbitrum (L1) gateway router supports calculating the L2 token address for any L1 ERC20.
ARBITRUM_L1_GATEWAY_ROUTER_DEFAULT = "0x72Ce9c846789fdB6fC1f34aC4AD25Dd9ef7031ef"

# ERC20 Transfer(address,address,uint256)
TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Common DEX swap event topics (topic0). These are chain-agnostic and can be detected from tx receipts.
# Computed via `cast sig-event ...`.
TOPIC0_UNISWAP_V2_SWAP = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
TOPIC0_UNISWAP_V3_SWAP = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
TOPIC0_CURVE_TOKEN_EXCHANGE = "0x8b3e96f2b889fa771c53c981b40daf005f63f637f1869f707052d15a3dd97140"
TOPIC0_CURVE_TOKEN_EXCHANGE_UNDERLYING = "0xd013ca23e77a65003c2c659c5442c00c805371b7fc1ebd4c206c41d1536bd90b"
TOPIC0_BALANCER_V2_SWAP = "0x2170c741c41531aec20e7c107c24eecfdd15e69c9bb0a8dd37b1840b9e0b207b"

DEX_SWAP_TOPIC0: set[str] = {
    TOPIC0_UNISWAP_V2_SWAP,
    TOPIC0_UNISWAP_V3_SWAP,
    TOPIC0_CURVE_TOKEN_EXCHANGE,
    TOPIC0_CURVE_TOKEN_EXCHANGE_UNDERLYING,
    TOPIC0_BALANCER_V2_SWAP,
}

# Arbitrum L1 gateway router deposit selector (also used in existing Arbitrum bridge-out tooling).
# cast sig "outboundTransfer(address,address,uint256,bytes)" -> 0x7b3a3c8b
SELECTOR_OUTBOUND_TRANSFER = "0x7b3a3c8b"

# cast sig "getGateway(address)" -> 0xbda009fe
SEL_GET_GATEWAY = "0xbda009fe"

# cast sig "calculateL2TokenAddress(address)" -> 0xa7e28d48
SEL_CALCULATE_L2_TOKEN_ADDRESS = "0xa7e28d48"

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


def _eth_get_block(client: RpcClient, block_number: int) -> Dict[str, Any]:
    blk = _rpc_with_retries(client, "eth_getBlockByNumber", [hex(int(block_number)), False])
    if not isinstance(blk, dict):
        raise RpcError(f"unexpected eth_getBlockByNumber result: {type(blk)}")
    return blk


def _eth_block_timestamp(client: RpcClient, block_number: int, cache: Dict[int, int]) -> int:
    bn = int(block_number)
    if bn in cache:
        return int(cache[bn])
    blk = _eth_get_block(client, bn)
    ts = _hex_to_int(str(blk.get("timestamp") or "0x0"))
    cache[bn] = int(ts)
    return int(ts)


def _eth_get_transaction(client: RpcClient, tx_hash: str, cache: Dict[str, Dict[str, Any] | None]) -> Dict[str, Any] | None:
    txh = str(tx_hash).lower()
    if txh in cache:
        return cache[txh]
    tx = _rpc_with_retries(client, "eth_getTransactionByHash", [txh])
    if tx is None:
        cache[txh] = None
        return None
    if not isinstance(tx, dict):
        raise RpcError(f"unexpected eth_getTransactionByHash result: {type(tx)}")
    cache[txh] = tx
    return tx


def _eth_get_transaction_receipt(client: RpcClient, tx_hash: str, cache: Dict[str, Dict[str, Any] | None]) -> Dict[str, Any] | None:
    txh = str(tx_hash).lower()
    if txh in cache:
        return cache[txh]
    rcpt = _rpc_with_retries(client, "eth_getTransactionReceipt", [txh])
    if rcpt is None:
        cache[txh] = None
        return None
    if not isinstance(rcpt, dict):
        raise RpcError(f"unexpected eth_getTransactionReceipt result: {type(rcpt)}")
    cache[txh] = rcpt
    return rcpt


def _tx_selector(input_hex: str | None) -> str | None:
    s = str(input_hex or "").lower()
    if not s.startswith("0x") or len(s) < 10:
        return None
    return "0x" + s[2:10]


def _receipt_topic0_hits(receipt: Dict[str, Any] | None, topic0_set: set[str]) -> List[str]:
    if not receipt or not isinstance(receipt, dict):
        return []
    logs = receipt.get("logs") or []
    hits: set[str] = set()
    for log in logs:
        if not isinstance(log, dict):
            continue
        topics = log.get("topics") or []
        if not topics:
            continue
        t0 = str(topics[0] or "").lower()
        if t0 in topic0_set:
            hits.add(t0)
    return sorted(hits)


def _abi_word_address(addr: str) -> str:
    a = _normalize_address(addr)
    return "0" * 24 + a[2:]


def _eth_call(client: RpcClient, *, to_addr: str, data: str, block_tag: str = "latest") -> str:
    res = _rpc_with_retries(client, "eth_call", [{"to": _normalize_address(to_addr), "data": str(data)}, str(block_tag)])
    return str(res or "")


def _eth_call_address(client: RpcClient, *, to_addr: str, data: str, block_tag: str = "latest") -> str:
    res = _eth_call(client, to_addr=to_addr, data=data, block_tag=block_tag)
    s = str(res).lower()
    if not s.startswith("0x") or len(s) < 66:
        raise RpcError(f"unexpected eth_call address result: {res!r}")
    return _normalize_address("0x" + s[-40:])


def _calculate_arbitrum_l2_token_address(
    eth: RpcClient,
    *,
    l1_gateway_router: str,
    l1_token: str,
    cache: Dict[str, str],
) -> str:
    """Resolve Arbitrum One L2 token address for a given L1 token via the L1 gateway router."""

    l1 = _normalize_address(l1_token)
    if l1 in cache:
        return cache[l1]

    call_data = SEL_CALCULATE_L2_TOKEN_ADDRESS + _abi_word_address(l1)
    l2 = _eth_call_address(eth, to_addr=_normalize_address(l1_gateway_router), data=call_data)
    cache[l1] = l2
    return l2


def _arbitrum_l1_gateway_for_token(
    eth: RpcClient,
    *,
    l1_gateway_router: str,
    l1_token: str,
    cache: Dict[str, str],
) -> str:
    """Resolve the Arbitrum One L1 gateway contract used for a given L1 ERC20 token."""

    l1 = _normalize_address(l1_token)
    if l1 in cache:
        return cache[l1]

    call_data = SEL_GET_GATEWAY + _abi_word_address(l1)
    gw = _eth_call_address(eth, to_addr=_normalize_address(l1_gateway_router), data=call_data)
    cache[l1] = gw
    return gw


def _decode_outbound_transfer(calldata_hex: str) -> Dict[str, Any]:
    """
    Decode `outboundTransfer(address,address,uint256,bytes)` call data.

    ABI layout:
    - 4 bytes selector
    - 4 x 32-byte words: token, to, amount, offset(data)
    - dynamic bytes tail: len, data
    """

    if not calldata_hex or not calldata_hex.startswith("0x"):
        raise ValueError("calldata must be 0x-prefixed")
    if len(calldata_hex) < 10:
        raise ValueError("calldata too short")

    selector = "0x" + calldata_hex[2:10].lower()
    if selector != SELECTOR_OUTBOUND_TRANSFER:
        raise ValueError(f"unexpected selector: {selector}")

    args_hex = calldata_hex[10:]
    if len(args_hex) < 64 * 4:
        raise ValueError("calldata args too short")

    def word(i: int) -> str:
        return args_hex[i * 64 : (i + 1) * 64]

    token_word = word(0)
    to_word = word(1)
    amount_word = word(2)
    offset_word = word(3)

    token = _normalize_address("0x" + token_word[-40:])
    to = _normalize_address("0x" + to_word[-40:])
    amount = int(amount_word, 16)
    offset = int(offset_word, 16)

    data_offset_hex = offset * 2
    if data_offset_hex + 64 > len(args_hex):
        raise ValueError("data offset out of bounds")
    data_len = int(args_hex[data_offset_hex : data_offset_hex + 64], 16)
    data_start = data_offset_hex + 64
    data_end = data_start + (data_len * 2)
    if data_end > len(args_hex):
        raise ValueError("data length out of bounds")
    data = "0x" + args_hex[data_start:data_end]

    return {
        "selector": selector,
        "token": token,
        "to": to,
        "amount": int(amount),
        "data": data,
    }


def _find_block_at_or_after_timestamp(
    client: RpcClient,
    *,
    target_ts: int,
    low_block: int,
    high_block: int,
    ts_cache: Dict[int, int],
) -> int:
    """
    Binary-search the first block whose timestamp >= target_ts.

    Uses eth_getBlockByNumber; caches block->timestamp in ts_cache.
    """

    low = int(max(0, low_block))
    high = int(max(low, high_block))
    target = int(target_ts)

    while low < high:
        mid = (low + high) // 2
        mid_ts = _eth_block_timestamp(client, mid, ts_cache)
        if mid_ts < target:
            low = mid + 1
        else:
            high = mid
    return int(low)


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


@dataclass(frozen=True)
class ArbitrumBridgeDeposit:
    """Best-effort Arbitrum One bridge deposit detected via L1 gateway router outboundTransfer()."""

    block_number: int
    tx_hash: str
    l2_to: str
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


def _scan_arbitrum_bridge_deposits(
    eth: RpcClient,
    *,
    outgoing_transfers: List[OutgoingTransfer],
    l1_token_addr: str,
    l1_token_gateway: str | None,
    l1_gateway_router: str,
    tx_cache: Dict[str, Dict[str, Any] | None],
) -> List[ArbitrumBridgeDeposit]:
    """
    Detect Arbitrum deposits for this token by inspecting tx calldata.

    We use outgoing token Transfer logs (from sender) and then check whether the tx is a call to the
    Arbitrum L1 gateway router with selector outboundTransfer(address,address,uint256,bytes).

    This catches deposits *initiated by the sender address*. It does not catch "sender -> contract -> bridge"
    patterns where a contract bridges on the sender's behalf.
    """

    deposits: List[ArbitrumBridgeDeposit] = []
    seen_tx: set[str] = set()
    token_norm = _normalize_address(l1_token_addr)
    router_norm = _normalize_address(l1_gateway_router)
    gateway_norm: str | None = None
    if l1_token_gateway:
        try:
            gateway_norm = _normalize_address(str(l1_token_gateway))
        except Exception:
            gateway_norm = None
    allowed_call_targets = {router_norm}
    if gateway_norm:
        allowed_call_targets.add(gateway_norm)

    for t in outgoing_transfers:
        if gateway_norm:
            try:
                if _normalize_address(str(t.to_addr)) != gateway_norm:
                    continue
            except Exception:
                continue

        txh = str(t.tx_hash).lower()
        if not txh or txh in seen_tx:
            continue
        seen_tx.add(txh)

        tx = _eth_get_transaction(eth, txh, tx_cache)
        if not tx:
            continue

        to_addr = tx.get("to")
        if not to_addr:
            continue
        try:
            if _normalize_address(str(to_addr)) not in allowed_call_targets:
                continue
        except Exception:
            continue

        input_data = str(tx.get("input") or "").lower()
        if not input_data.startswith(SELECTOR_OUTBOUND_TRANSFER):
            continue

        try:
            decoded = _decode_outbound_transfer(input_data)
        except Exception:
            continue

        try:
            if _normalize_address(str(decoded.get("token") or "")) != token_norm:
                continue
            l2_to = _normalize_address(str(decoded.get("to") or "0x0000000000000000000000000000000000000000"))
            amount_wei = int(decoded.get("amount") or 0)
        except Exception:
            continue

        if amount_wei <= 0:
            continue

        deposits.append(ArbitrumBridgeDeposit(block_number=int(t.block_number), tx_hash=txh, l2_to=l2_to, amount_wei=int(amount_wei)))

    deposits.sort(key=lambda x: (x.block_number, x.tx_hash))
    return deposits


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
        "--classify-unknown-eoa-behavior",
        action="store_true",
        help="Heuristic: for unlabeled EOAs (recipients), classify post-exit behavior as bridger/exchange-depositor/dex-trader/self-custody (best-effort).",
    )
    parser.add_argument(
        "--heuristic-max-txs-per-exit",
        type=int,
        default=3,
        help="When classifying unknown EOAs, max outgoing-token txs per exit event to inspect via eth_getTransactionReceipt (tradeoff: recall vs RPC load).",
    )
    parser.add_argument(
        "--include-arbitrum-followup",
        action="store_true",
        help="Detect Arbitrum L1 gateway deposits after exits (outboundTransfer) and follow token transfers on Arbitrum (best-effort).",
    )
    parser.add_argument("--arbitrum-rpc", default=os.environ.get("ARBITRUM_RPC_URL") or ARBITRUM_RPC_DEFAULT)
    parser.add_argument("--arbitrum-l1-gateway-router", default=ARBITRUM_L1_GATEWAY_ROUTER_DEFAULT)
    parser.add_argument(
        "--arbitrum-followup-window-days",
        type=int,
        default=7,
        help="After a detected Arbitrum deposit, how long to watch Arbitrum transfers for exchange routing (days, by timestamp).",
    )
    parser.add_argument(
        "--arbitrum-include-second-hop",
        action="store_true",
        help="Arbitrum follow-up: also check one intermediate hop before reaching an exchange (recipient → intermediate → exchange).",
    )

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
    dex_router_addrs: set[str] = set()
    bridge_addrs: set[str] = set()
    for addr, meta in labels.items():
        try:
            a = _normalize_address(addr)
        except Exception:
            continue
        if isinstance(meta, dict) and str(meta.get("category") or "") == "exchange":
            exchange_labels[a] = meta
        else:
            labeled_non_exchange_addrs.add(a)
            if isinstance(meta, dict) and str(meta.get("category") or "") == "dex_router":
                dex_router_addrs.add(a)
            if isinstance(meta, dict) and str(meta.get("category") or "") == "bridge":
                bridge_addrs.add(a)

    exchange_addrs = sorted(exchange_labels.keys())
    exchange_topics = [_pad_topic_address(a) for a in exchange_addrs]

    eth = RpcClient(str(args.eth_rpc))
    latest_block = _eth_block_number(eth)
    to_block = int(latest_block)
    from_block = max(0, to_block - int(args.days) * int(args.blocks_per_day))
    window_blocks = int(args.window_days) * int(args.blocks_per_day)

    tx_cache: Dict[str, Dict[str, Any] | None] = {}
    receipt_cache: Dict[str, Dict[str, Any] | None] = {}
    eth_block_ts_cache: Dict[int, int] = {}

    classify_unknown_eoa_behavior = bool(args.classify_unknown_eoa_behavior)
    heuristic_max_txs_per_exit = max(0, int(args.heuristic_max_txs_per_exit))

    include_arbitrum_followup = bool(args.include_arbitrum_followup)
    arbitrum_followup_window_days = int(args.arbitrum_followup_window_days)
    arb_l1_gateway_router = _normalize_address(str(args.arbitrum_l1_gateway_router))
    arb: RpcClient | None = None
    arb_latest_block: int | None = None
    arb_latest_ts: int | None = None
    arb_block_ts_cache: Dict[int, int] = {}
    arb_l2_token_addr: str | None = None
    arb_l2_token_cache: Dict[str, str] = {}
    arb_l1_token_gateway: str | None = None
    arb_gateway_cache: Dict[str, str] = {}

    need_arbitrum_bridge_detection = bool(include_arbitrum_followup or classify_unknown_eoa_behavior)

    if need_arbitrum_bridge_detection:
        try:
            arb_l1_token_gateway = _arbitrum_l1_gateway_for_token(
                eth,
                l1_gateway_router=arb_l1_gateway_router,
                l1_token=token_addr,
                cache=arb_gateway_cache,
            )
        except Exception:
            arb_l1_token_gateway = None

    if include_arbitrum_followup:
        arb = RpcClient(str(args.arbitrum_rpc), user_agent="livepeer-delegation-research/erc20-exit-routing-arbitrum")
        arb_latest_block = _eth_block_number(arb)
        arb_latest_ts = _eth_block_timestamp(arb, int(arb_latest_block), arb_block_ts_cache)
        arb_l2_token_addr = _calculate_arbitrum_l2_token_address(
            eth,
            l1_gateway_router=arb_l1_gateway_router,
            l1_token=token_addr,
            cache=arb_l2_token_cache,
        )

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
    arb_deposits_by_recipient: Dict[str, List[ArbitrumBridgeDeposit]] = {}

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
        if need_arbitrum_bridge_detection or args.include_second_hop or args.include_third_hop or args.classify_first_hop_dests or classify_unknown_eoa_behavior:
            print(f"scan outgoing: recipient={addr_norm} (range {transfer_from_block:,}..{transfer_to_block:,})")
            outgoing_transfers_by_recipient[addr_norm] = _scan_outgoing_transfers(
                eth,
                token_addr=token_addr,
                from_addr=addr_norm,
                from_block=transfer_from_block,
                to_block=transfer_to_block,
                chunk_size=int(args.log_chunk_size),
            )
        if need_arbitrum_bridge_detection:
            outgoing_for_addr = outgoing_transfers_by_recipient.get(addr_norm) or []
            if outgoing_for_addr:
                print(f"scan Arbitrum deposits: sender={addr_norm}")
                arb_deposits_by_recipient[addr_norm] = _scan_arbitrum_bridge_deposits(
                    eth,
                    outgoing_transfers=outgoing_for_addr,
                    l1_token_addr=token_addr,
                    l1_token_gateway=arb_l1_token_gateway,
                    l1_gateway_router=arb_l1_gateway_router,
                    tx_cache=tx_cache,
                )

    banned_intermediates = {token_addr, exit_contract, _normalize_address("0x0000000000000000000000000000000000000000")}
    banned_intermediates.update(labeled_non_exchange_addrs)
    arb_banned_intermediates: set[str] = set(banned_intermediates)
    if include_arbitrum_followup and arb_l2_token_addr:
        arb_banned_intermediates.add(_normalize_address(str(arb_l2_token_addr)))

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

    unknown_eoa_behavior: Dict[str, Any] | None = None
    unknown_eoa_behavior_counts: Counter[str] = Counter()
    unknown_eoa_behavior_exit_wei: Dict[str, int] = defaultdict(int)
    unknown_eoa_behavior_examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    unknown_eoa_behavior_total_events = 0
    unknown_eoa_behavior_total_exit_wei = 0

    def _is_unknown_eoa(addr: str) -> bool:
        a = _normalize_address(addr)
        if a in exchange_labels or a in labeled_non_exchange_addrs:
            return False
        return not _is_contract_address(eth, a, intermediate_code_cache)

    def _record_unknown_eoa_behavior(kind: str, confidence: str, *, exit_wei: int, example: Dict[str, Any]) -> None:
        nonlocal unknown_eoa_behavior_total_events, unknown_eoa_behavior_total_exit_wei
        key = f"{kind}:{confidence}"
        unknown_eoa_behavior_counts[key] += 1
        unknown_eoa_behavior_exit_wei[key] += int(exit_wei)
        unknown_eoa_behavior_total_events += 1
        unknown_eoa_behavior_total_exit_wei += int(exit_wei)
        if len(unknown_eoa_behavior_examples[kind]) < 25:
            unknown_eoa_behavior_examples[kind].append(example)

    def _classify_unknown_eoa_non_exchange(
        *,
        e: ExitEvent,
        recipient_norm: str,
        end_block: int,
        outgoing_all: List[OutgoingTransfer],
        deposit: ArbitrumBridgeDeposit | None,
        dex_router_interaction: bool,
        dex_router_to: str | None,
        dex_router_label: str | None,
        dex_router_tx: str | None,
    ) -> tuple[str, str, Dict[str, Any]]:
        # Bridger: decoded Arbitrum outboundTransfer() deposit (highest-confidence bridge signal in this tool).
        if deposit is not None:
            return (
                "bridger",
                "high",
                {
                    "bridge": "arbitrum",
                    "deposit_tx": str(deposit.tx_hash),
                    "deposit_block": int(deposit.block_number),
                    "l2_to": str(deposit.l2_to),
                    "deposit_token_amount": str(_wei_to_token(deposit.amount_wei)),
                },
            )

        # DEX trader: detect swap topics in tx receipts for a small number of token-moving txs (best-effort).
        hits_best: List[str] = []
        hits_tx: str | None = None
        tx_to: str | None = None
        tx_selector: str | None = None

        if heuristic_max_txs_per_exit > 0 and outgoing_all:
            candidates = [t for t in outgoing_all if int(t.block_number) > int(e.block_number) and int(t.block_number) <= int(end_block)]
            # Prefer the largest token-moving txs in-window; this catches swaps even if the first outflow is small/noisy.
            candidates.sort(key=lambda x: (-int(x.amount_wei), int(x.block_number), x.tx_hash))
            candidates = candidates[: int(heuristic_max_txs_per_exit)]
            for t in candidates:
                txh = str(t.tx_hash)
                rcpt = _eth_get_transaction_receipt(eth, txh, receipt_cache)
                hits = _receipt_topic0_hits(rcpt, DEX_SWAP_TOPIC0)
                if hits:
                    hits_best = hits
                    hits_tx = txh
                    tx = _eth_get_transaction(eth, txh, tx_cache) or {}
                    try:
                        if tx.get("to"):
                            tx_to = _normalize_address(str(tx.get("to")))
                    except Exception:
                        tx_to = None
                    tx_selector = _tx_selector(tx.get("input"))
                    break

        if hits_best:
            return (
                "dex_trader",
                "high",
                {
                    "swap_topic0_hits": hits_best,
                    "tx": str(hits_tx),
                    "tx_to": tx_to,
                    "tx_selector": tx_selector,
                },
            )

        if dex_router_interaction:
            return (
                "dex_trader",
                "medium",
                {
                    "method": "tx.to in labels[dex_router]",
                    "dex_router_to": dex_router_to,
                    "dex_router_label": dex_router_label,
                    "dex_router_tx": dex_router_tx,
                },
            )

        # Self-custody: no observed token outflows within window (strongest "held" signal).
        if not outgoing_all:
            return ("self_custody", "high", {"method": "no ERC20 Transfer(from=recipient) observed in scanned range"})

        out_in_window = [t for t in outgoing_all if int(t.block_number) > int(e.block_number) and int(t.block_number) <= int(end_block)]
        if not out_in_window:
            return ("self_custody", "high", {"method": "no token outflows within window"})

        # Weak self-custody signal: first token outflow goes to an EOA (wallet re-org / OTC / unlabeled CEX all possible).
        first = out_in_window[0]
        to_addr = _normalize_address(str(first.to_addr))
        to_is_contract = _is_contract_address(eth, to_addr, intermediate_code_cache)
        if not to_is_contract:
            return (
                "self_custody",
                "low",
                {
                    "method": "first token outflow destination is EOA",
                    "first_outflow_tx": str(first.tx_hash),
                    "first_outflow_block": int(first.block_number),
                    "first_outflow_to": to_addr,
                    "first_outflow_amount": str(_wei_to_token(first.amount_wei)),
                },
            )

        return (
            "self_custody",
            "low",
            {
                "method": "no exchange/bridge/dex signal; first token outflow goes to contract",
                "first_outflow_tx": str(first.tx_hash),
                "first_outflow_block": int(first.block_number),
                "first_outflow_to": to_addr,
                "first_outflow_amount": str(_wei_to_token(first.amount_wei)),
            },
        )

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

    # Cross-chain follow-up (Ethereum -> Arbitrum bridge deposit -> exchange routing on Arbitrum).
    arb_bridge_deposit_event_count = 0
    arb_bridge_deposit_exit_wei = 0
    arb_bridge_deposit_token_wei = 0
    arb_matched_exchange_event_count = 0
    arb_matched_exchange_exit_wei = 0
    arb_matched_exchange_token_wei = 0
    arb_exchange_counter: Counter[str] = Counter()
    arb_bridge_examples: List[Dict[str, Any]] = []
    arb_matched_exchange_examples: List[Dict[str, Any]] = []
    arb_exchange_transfers_from_cache: Dict[str, Dict[str, Any]] = {}
    arb_outgoing_transfers_from_cache: Dict[str, Dict[str, Any]] = {}

    # Post-exit "role" classification (heuristic; complements strict exchange routing).
    role_counter_events: Counter[str] = Counter()
    role_counter_exit_wei: Dict[str, int] = defaultdict(int)
    role_examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    # Addresses that appear as intermediates on paths that end at labeled exchanges.
    exchange_intermediate_counter: Counter[str] = Counter()
    exchange_intermediate_exit_wei: Dict[str, int] = defaultdict(int)
    exchange_intermediate_is_contract: Dict[str, bool] = {}
    exchange_intermediate_example: Dict[str, Dict[str, Any]] = {}

    # Process chronologically so caches tend to extend forward only.
    for e in considered_exits:
        end_block = int(e.block_number + window_blocks)
        recipient_norm = _normalize_address(e.recipient)
        classify_this_unknown_eoa = bool(classify_unknown_eoa_behavior) and _is_unknown_eoa(recipient_norm)
        unknown_eoa_behavior_recorded = False

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

        deposit: ArbitrumBridgeDeposit | None = None
        if need_arbitrum_bridge_detection:
            deposits = arb_deposits_by_recipient.get(recipient_norm) or []
            for d in deposits:
                if int(d.block_number) <= int(e.block_number):
                    continue
                if int(d.block_number) > int(end_block):
                    break
                deposit = d
                break

        # Heuristic: detect whether the recipient interacted with a labeled DEX router in a tx that also moved tokens.
        dex_router_interaction = False
        dex_router_to: str | None = None
        dex_router_label: str | None = None
        dex_router_tx: str | None = None
        if outgoing_all and threshold_wei > 0 and dex_router_addrs:
            for t in outgoing_all:
                if t.block_number <= e.block_number:
                    continue
                if t.block_number > end_block:
                    break
                if int(t.amount_wei) < int(threshold_wei):
                    continue
                tx = _eth_get_transaction(eth, str(t.tx_hash), tx_cache)
                if not tx:
                    continue
                to_addr = tx.get("to")
                if not to_addr:
                    continue
                try:
                    to_norm = _normalize_address(str(to_addr))
                except Exception:
                    continue
                if to_norm in dex_router_addrs:
                    dex_router_interaction = True
                    dex_router_to = to_norm
                    dex_router_label = str(labels.get(to_norm, {}).get("name") or "") if isinstance(labels, dict) else None
                    dex_router_tx = str(t.tx_hash)
                    break

        role_recorded = False

        def _record_role(role: str) -> None:
            nonlocal role_recorded
            if role_recorded:
                return
            role_norm = str(role or "unknown")
            role_counter_events[role_norm] += 1
            role_counter_exit_wei[role_norm] += int(e.amount_wei)
            if len(role_examples[role_norm]) < 15:
                role_examples[role_norm].append(
                    {
                        "exit_block": int(e.block_number),
                        "exit_tx": str(e.tx_hash),
                        "recipient": str(e.recipient),
                        "exit_amount": str(_wei_to_token(e.amount_wei)),
                        "first_hop_category": str(firsthop_category),
                        "first_hop_to": firsthop_to,
                        "first_hop_is_contract": firsthop_is_contract,
                        "arbitrum_bridge_deposit_detected": bool(deposit is not None),
                        "dex_router_interaction": bool(dex_router_interaction),
                        "dex_router_to": dex_router_to,
                        "dex_router_label": dex_router_label,
                        "dex_router_tx": dex_router_tx,
                    }
                )
            role_recorded = True

        # Optional follow-up: detect Arbitrum bridge deposits after exit and check if the bridged tokens
        # route into labeled exchange endpoints on Arbitrum (best-effort lower bound).
        if include_arbitrum_followup and arb is not None and arb_latest_block is not None and arb_latest_ts is not None and arb_l2_token_addr is not None:
            if deposit is not None:
                arb_bridge_deposit_event_count += 1
                arb_bridge_deposit_exit_wei += int(e.amount_wei)
                arb_bridge_deposit_token_wei += int(deposit.amount_wei)

                deposit_ts = _eth_block_timestamp(eth, int(deposit.block_number), eth_block_ts_cache)
                if len(arb_bridge_examples) < 25:
                    arb_bridge_examples.append(
                        {
                            "exit_block": int(e.block_number),
                            "exit_tx": str(e.tx_hash),
                            "recipient": str(e.recipient),
                            "exit_amount": str(_wei_to_token(e.amount_wei)),
                            "l1_deposit_block": int(deposit.block_number),
                            "l1_deposit_tx": str(deposit.tx_hash),
                            "l2_recipient": str(deposit.l2_to),
                            "deposit_amount": str(_wei_to_token(deposit.amount_wei)),
                            "deposit_block_timestamp": int(deposit_ts),
                        }
                    )

                # Map L1 deposit timestamp into an Arbitrum block range, then look for transfers into labeled exchanges.
                try:
                    arb_start_block = _find_block_at_or_after_timestamp(
                        arb,
                        target_ts=int(deposit_ts),
                        low_block=0,
                        high_block=int(arb_latest_block),
                        ts_cache=arb_block_ts_cache,
                    )
                except Exception:
                    arb_start_block = 0

                followup_end_ts = int(deposit_ts + arbitrum_followup_window_days * 86400)
                if followup_end_ts >= int(arb_latest_ts):
                    arb_end_block = int(arb_latest_block)
                else:
                    try:
                        arb_end_block = _find_block_at_or_after_timestamp(
                            arb,
                            target_ts=followup_end_ts,
                            low_block=int(arb_start_block),
                            high_block=int(arb_latest_block),
                            ts_cache=arb_block_ts_cache,
                        )
                    except Exception:
                        arb_end_block = int(arb_latest_block)

                if arb_start_block <= arb_end_block:
                    # Direct: L2 recipient -> labeled exchange
                    l2_sender = _normalize_address(str(deposit.l2_to))
                    cache = arb_exchange_transfers_from_cache.get(l2_sender)
                    if cache is None:
                        try:
                            fetched = _scan_exchange_transfers_from(
                                arb,
                                token_addr=str(arb_l2_token_addr),
                                from_addr=l2_sender,
                                from_block=int(arb_start_block),
                                to_block=int(arb_end_block),
                                exchange_topics=exchange_topics,
                                chunk_size=int(args.log_chunk_size),
                            )
                        except Exception:
                            fetched = []
                        cache = {"from_block": int(arb_start_block), "to_block": int(arb_end_block), "transfers": fetched}
                        arb_exchange_transfers_from_cache[l2_sender] = cache
                    else:
                        cached_from = int(cache.get("from_block") or 0)
                        cached_to = int(cache.get("to_block") or 0)
                        if int(arb_start_block) < cached_from:
                            try:
                                extra = _scan_exchange_transfers_from(
                                    arb,
                                    token_addr=str(arb_l2_token_addr),
                                    from_addr=l2_sender,
                                    from_block=int(arb_start_block),
                                    to_block=int(cached_from - 1),
                                    exchange_topics=exchange_topics,
                                    chunk_size=int(args.log_chunk_size),
                                )
                            except Exception:
                                extra = []
                            cache["from_block"] = int(arb_start_block)
                            cache["transfers"] = list(extra) + list(cache.get("transfers") or [])
                        if int(arb_end_block) > cached_to:
                            try:
                                extra = _scan_exchange_transfers_from(
                                    arb,
                                    token_addr=str(arb_l2_token_addr),
                                    from_addr=l2_sender,
                                    from_block=int(cached_to + 1),
                                    to_block=int(arb_end_block),
                                    exchange_topics=exchange_topics,
                                    chunk_size=int(args.log_chunk_size),
                                )
                            except Exception:
                                extra = []
                            cache["to_block"] = int(arb_end_block)
                            cache["transfers"] = list(cache.get("transfers") or []) + list(extra)

                    arb_direct = [
                        t
                        for t in (cache.get("transfers") or [])
                        if int(t.block_number) >= int(arb_start_block) and int(t.block_number) <= int(arb_end_block)
                    ]
                    direct_best = arb_direct[0] if arb_direct else None
                    if direct_best is not None:
                        arb_matched_exchange_event_count += 1
                        arb_matched_exchange_exit_wei += int(e.amount_wei)
                        arb_matched_exchange_token_wei += int(direct_best.amount_wei)
                        arb_exchange_counter[_normalize_address(direct_best.to_addr)] += 1
                        if len(arb_matched_exchange_examples) < 25:
                            arb_matched_exchange_examples.append(
                                {
                                    "exit_block": int(e.block_number),
                                    "exit_tx": str(e.tx_hash),
                                    "recipient": str(e.recipient),
                                    "exit_amount": str(_wei_to_token(e.amount_wei)),
                                    "l1_deposit_tx": str(deposit.tx_hash),
                                    "l2_recipient": str(deposit.l2_to),
                                    "arbitrum_start_block": int(arb_start_block),
                                    "arbitrum_end_block": int(arb_end_block),
                                    "exchange_to": str(direct_best.to_addr),
                                    "exchange_label": exchange_labels.get(_normalize_address(direct_best.to_addr), {}).get("name"),
                                    "exchange_tx": str(direct_best.tx_hash),
                                    "exchange_block": int(direct_best.block_number),
                                    "exchange_transfer_amount": str(_wei_to_token(direct_best.amount_wei)),
                                }
                            )
                    elif bool(args.arbitrum_include_second_hop):
                        # Second hop: L2 recipient -> intermediate -> labeled exchange (best-effort).
                        min_first_hop_fraction = Decimal(args.min_first_hop_fraction)
                        min_first_hop_wei_arb = max(
                            int((Decimal(args.min_first_hop_token) * scale).to_integral_value(rounding="ROUND_FLOOR")),
                            int((Decimal(int(deposit.amount_wei)) * min_first_hop_fraction).to_integral_value(rounding="ROUND_FLOOR")),
                        )

                        out_cache = arb_outgoing_transfers_from_cache.get(l2_sender)
                        if out_cache is None:
                            try:
                                fetched_out = _scan_outgoing_transfers(
                                    arb,
                                    token_addr=str(arb_l2_token_addr),
                                    from_addr=l2_sender,
                                    from_block=int(arb_start_block),
                                    to_block=int(arb_end_block),
                                    chunk_size=int(args.log_chunk_size),
                                )
                            except Exception:
                                fetched_out = []
                            out_cache = {"from_block": int(arb_start_block), "to_block": int(arb_end_block), "transfers": fetched_out}
                            arb_outgoing_transfers_from_cache[l2_sender] = out_cache
                        else:
                            cached_from = int(out_cache.get("from_block") or 0)
                            cached_to = int(out_cache.get("to_block") or 0)
                            if int(arb_start_block) < cached_from:
                                try:
                                    extra_out = _scan_outgoing_transfers(
                                        arb,
                                        token_addr=str(arb_l2_token_addr),
                                        from_addr=l2_sender,
                                        from_block=int(arb_start_block),
                                        to_block=int(cached_from - 1),
                                        chunk_size=int(args.log_chunk_size),
                                    )
                                except Exception:
                                    extra_out = []
                                out_cache["from_block"] = int(arb_start_block)
                                out_cache["transfers"] = list(extra_out) + list(out_cache.get("transfers") or [])
                            if int(arb_end_block) > cached_to:
                                try:
                                    extra_out = _scan_outgoing_transfers(
                                        arb,
                                        token_addr=str(arb_l2_token_addr),
                                        from_addr=l2_sender,
                                        from_block=int(cached_to + 1),
                                        to_block=int(arb_end_block),
                                        chunk_size=int(args.log_chunk_size),
                                    )
                                except Exception:
                                    extra_out = []
                                out_cache["to_block"] = int(arb_end_block)
                                out_cache["transfers"] = list(out_cache.get("transfers") or []) + list(extra_out)

                        arb_outgoing = [
                            t
                            for t in (out_cache.get("transfers") or [])
                            if int(t.block_number) >= int(arb_start_block) and int(t.block_number) <= int(arb_end_block)
                        ]

                        candidates: List[OutgoingTransfer] = []
                        for t in arb_outgoing:
                            to_norm = _normalize_address(t.to_addr)
                            if to_norm in arb_banned_intermediates or to_norm == _normalize_address(str(deposit.l2_to)):
                                continue
                            if to_norm in exchange_labels:
                                continue
                            if int(t.amount_wei) < int(min_first_hop_wei_arb):
                                continue
                            candidates.append(t)

                        candidates.sort(key=lambda x: (-int(x.amount_wei), int(x.block_number), x.tx_hash))
                        candidates = candidates[: max(0, int(args.max_first_hops_per_exit))]

                        best_second: Dict[str, Any] | None = None
                        for first in candidates:
                            intermediate = _normalize_address(first.to_addr)
                            if intermediate in arb_banned_intermediates:
                                continue

                            query_from = int(first.block_number + 1)
                            query_to = int(arb_end_block)
                            if query_from > query_to:
                                continue

                            cache2 = arb_exchange_transfers_from_cache.get(intermediate)
                            if cache2 is None:
                                try:
                                    fetched2 = _scan_exchange_transfers_from(
                                        arb,
                                        token_addr=str(arb_l2_token_addr),
                                        from_addr=intermediate,
                                        from_block=query_from,
                                        to_block=query_to,
                                        exchange_topics=exchange_topics,
                                        chunk_size=int(args.log_chunk_size),
                                    )
                                except Exception:
                                    fetched2 = []
                                cache2 = {"from_block": int(query_from), "to_block": int(query_to), "transfers": fetched2}
                                arb_exchange_transfers_from_cache[intermediate] = cache2
                            else:
                                cached_from = int(cache2.get("from_block") or 0)
                                cached_to = int(cache2.get("to_block") or 0)
                                if query_from < cached_from:
                                    try:
                                        extra = _scan_exchange_transfers_from(
                                            arb,
                                            token_addr=str(arb_l2_token_addr),
                                            from_addr=intermediate,
                                            from_block=int(query_from),
                                            to_block=int(cached_from - 1),
                                            exchange_topics=exchange_topics,
                                            chunk_size=int(args.log_chunk_size),
                                        )
                                    except Exception:
                                        extra = []
                                    cache2["from_block"] = int(query_from)
                                    cache2["transfers"] = list(extra) + list(cache2.get("transfers") or [])
                                if query_to > cached_to:
                                    try:
                                        extra = _scan_exchange_transfers_from(
                                            arb,
                                            token_addr=str(arb_l2_token_addr),
                                            from_addr=intermediate,
                                            from_block=int(cached_to + 1),
                                            to_block=int(query_to),
                                            exchange_topics=exchange_topics,
                                            chunk_size=int(args.log_chunk_size),
                                        )
                                    except Exception:
                                        extra = []
                                    cache2["to_block"] = int(query_to)
                                    cache2["transfers"] = list(cache2.get("transfers") or []) + list(extra)

                            t2_list = [t for t in (cache2.get("transfers") or []) if int(t.block_number) >= query_from and int(t.block_number) <= query_to]

                            if not t2_list:
                                continue
                            second = t2_list[0]
                            candidate_second: Dict[str, Any] = {
                                "exit_block": int(e.block_number),
                                "exit_tx": str(e.tx_hash),
                                "recipient": str(e.recipient),
                                "exit_amount": str(_wei_to_token(e.amount_wei)),
                                "l1_deposit_tx": str(deposit.tx_hash),
                                "l2_recipient": str(deposit.l2_to),
                                "first_hop_to": intermediate,
                                "first_hop_tx": str(first.tx_hash),
                                "first_hop_block": int(first.block_number),
                                "first_hop_amount": str(_wei_to_token(first.amount_wei)),
                                "second_hop_exchange_to": str(second.to_addr),
                                "second_hop_exchange_label": exchange_labels.get(_normalize_address(second.to_addr), {}).get("name"),
                                "second_hop_tx": str(second.tx_hash),
                                "second_hop_block": int(second.block_number),
                                "second_hop_exchange_amount_wei": int(second.amount_wei),
                                "second_hop_exchange_amount": str(_wei_to_token(second.amount_wei)),
                            }

                            if best_second is None:
                                best_second = candidate_second
                            else:
                                if int(candidate_second["second_hop_block"]) < int(best_second["second_hop_block"]):
                                    best_second = candidate_second
                                elif int(candidate_second["second_hop_block"]) == int(best_second["second_hop_block"]):
                                    if Decimal(candidate_second["first_hop_amount"]) > Decimal(best_second["first_hop_amount"]):
                                        best_second = candidate_second

                        if best_second is not None:
                            arb_matched_exchange_event_count += 1
                            arb_matched_exchange_exit_wei += int(e.amount_wei)
                            arb_matched_exchange_token_wei += int(best_second.get("second_hop_exchange_amount_wei") or 0)
                            exchange_to = _normalize_address(str(best_second["second_hop_exchange_to"]))
                            arb_exchange_counter[exchange_to] += 1
                            if len(arb_matched_exchange_examples) < 25:
                                arb_matched_exchange_examples.append(best_second)

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
            _record_role("exchange_strict")
            if classify_this_unknown_eoa and not unknown_eoa_behavior_recorded:
                _record_unknown_eoa_behavior(
                    "exchange_depositor",
                    "high",
                    exit_wei=int(e.amount_wei),
                    example={
                        "exit_block": int(e.block_number),
                        "exit_tx": str(e.tx_hash),
                        "recipient": str(e.recipient),
                        "exit_amount": str(_wei_to_token(e.amount_wei)),
                        "evidence": {
                            "hop": 1,
                            "exchange_to": str(direct_best.to_addr),
                            "exchange_label": exchange_labels.get(_normalize_address(direct_best.to_addr), {}).get("name"),
                            "exchange_tx": str(direct_best.tx_hash),
                            "exchange_block": int(direct_best.block_number),
                            "exchange_transfer_amount": str(_wei_to_token(direct_best.amount_wei)),
                        },
                    },
                )
                unknown_eoa_behavior_recorded = True
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
            if deposit is not None:
                _record_role("bridge_deposit")
            elif dex_router_interaction:
                _record_role("dex_router_interaction")
            elif firsthop_category == "no_first_hop_meeting_threshold":
                _record_role("hold_no_first_hop")
            else:
                _record_role(firsthop_category)
            if classify_this_unknown_eoa and not unknown_eoa_behavior_recorded:
                kind, confidence, evidence = _classify_unknown_eoa_non_exchange(
                    e=e,
                    recipient_norm=recipient_norm,
                    end_block=end_block,
                    outgoing_all=outgoing_all,
                    deposit=deposit,
                    dex_router_interaction=dex_router_interaction,
                    dex_router_to=dex_router_to,
                    dex_router_label=dex_router_label,
                    dex_router_tx=dex_router_tx,
                )
                _record_unknown_eoa_behavior(
                    kind,
                    confidence,
                    exit_wei=int(e.amount_wei),
                    example={
                        "exit_block": int(e.block_number),
                        "exit_tx": str(e.tx_hash),
                        "recipient": str(e.recipient),
                        "exit_amount": str(_wei_to_token(e.amount_wei)),
                        "first_hop_to": firsthop_to,
                        "first_hop_is_contract": firsthop_is_contract,
                        "evidence": evidence,
                    },
                )
                unknown_eoa_behavior_recorded = True
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
            _record_role("exchange_strict")
            if classify_this_unknown_eoa and not unknown_eoa_behavior_recorded:
                _record_unknown_eoa_behavior(
                    "exchange_depositor",
                    "medium",
                    exit_wei=int(e.amount_wei),
                    example={
                        "exit_block": int(e.block_number),
                        "exit_tx": str(e.tx_hash),
                        "recipient": str(e.recipient),
                        "exit_amount": str(_wei_to_token(e.amount_wei)),
                        "evidence": {
                            "hop": 2,
                            "first_hop_to": str(best_second.get("first_hop_to")),
                            "first_hop_tx": str(best_second.get("first_hop_tx")),
                            "second_hop_exchange_to": str(best_second.get("second_hop_exchange_to")),
                            "second_hop_exchange_label": str(best_second.get("second_hop_exchange_label")),
                            "second_hop_tx": str(best_second.get("second_hop_tx")),
                            "second_hop_block": int(best_second.get("second_hop_block") or 0),
                        },
                    },
                )
                unknown_eoa_behavior_recorded = True
            matched_second_exit_wei += int(e.amount_wei)
            matched_second_event_count += 1
            exchange_counter_second[_normalize_address(str(best_second["second_hop_exchange_to"]))] += 1
            if len(matched_second_events) < 25:
                matched_second_events.append(best_second)
            try:
                inter = _normalize_address(str(best_second.get("first_hop_to") or ""))
                exchange_intermediate_counter[inter] += 1
                exchange_intermediate_exit_wei[inter] += int(e.amount_wei)
                if bool(args.classify_intermediates) and best_second.get("first_hop_intermediate_is_contract") is not None:
                    exchange_intermediate_is_contract[inter] = bool(best_second.get("first_hop_intermediate_is_contract"))
                if inter not in exchange_intermediate_example:
                    exchange_intermediate_example[inter] = {
                        "first_hop_to": inter,
                        "first_hop_intermediate_is_contract": exchange_intermediate_is_contract.get(inter),
                        "example_exit_tx": str(best_second.get("exit_tx") or ""),
                        "example_first_hop_tx": str(best_second.get("first_hop_tx") or ""),
                        "example_exchange_to": str(best_second.get("second_hop_exchange_to") or ""),
                        "example_exchange_label": str(best_second.get("second_hop_exchange_label") or ""),
                    }
            except Exception:
                pass
            continue

        if best_third is not None:
            _record_role("exchange_strict")
            if classify_this_unknown_eoa and not unknown_eoa_behavior_recorded:
                _record_unknown_eoa_behavior(
                    "exchange_depositor",
                    "low",
                    exit_wei=int(e.amount_wei),
                    example={
                        "exit_block": int(e.block_number),
                        "exit_tx": str(e.tx_hash),
                        "recipient": str(e.recipient),
                        "exit_amount": str(_wei_to_token(e.amount_wei)),
                        "evidence": {
                            "hop": 3,
                            "first_hop_to": str(best_third.get("first_hop_to")),
                            "first_hop_tx": str(best_third.get("first_hop_tx")),
                            "second_hop_to": str(best_third.get("second_hop_to")),
                            "second_hop_tx": str(best_third.get("second_hop_tx")),
                            "third_hop_exchange_to": str(best_third.get("third_hop_exchange_to")),
                            "third_hop_exchange_label": str(best_third.get("third_hop_exchange_label")),
                            "third_hop_tx": str(best_third.get("third_hop_tx")),
                            "third_hop_block": int(best_third.get("third_hop_block") or 0),
                        },
                    },
                )
                unknown_eoa_behavior_recorded = True
            matched_third_exit_wei += int(e.amount_wei)
            matched_third_event_count += 1
            exchange_counter_third[_normalize_address(str(best_third["third_hop_exchange_to"]))] += 1
            if len(matched_third_events) < 25:
                matched_third_events.append(best_third)
            # Third-hop intermediates are noisier; we only track hop-1 for now.
            try:
                inter = _normalize_address(str(best_third.get("first_hop_to") or ""))
                exchange_intermediate_counter[inter] += 1
                exchange_intermediate_exit_wei[inter] += int(e.amount_wei)
                if bool(args.classify_intermediates) and best_third.get("first_hop_intermediate_is_contract") is not None:
                    exchange_intermediate_is_contract[inter] = bool(best_third.get("first_hop_intermediate_is_contract"))
                if inter not in exchange_intermediate_example:
                    exchange_intermediate_example[inter] = {
                        "first_hop_to": inter,
                        "first_hop_intermediate_is_contract": exchange_intermediate_is_contract.get(inter),
                        "example_exit_tx": str(best_third.get("exit_tx") or ""),
                        "example_first_hop_tx": str(best_third.get("first_hop_tx") or ""),
                        "example_exchange_to": str(best_third.get("third_hop_exchange_to") or ""),
                        "example_exchange_label": str(best_third.get("third_hop_exchange_label") or ""),
                    }
            except Exception:
                pass

        if not role_recorded:
            if deposit is not None:
                _record_role("bridge_deposit")
            elif dex_router_interaction:
                _record_role("dex_router_interaction")
            elif firsthop_category == "no_first_hop_meeting_threshold":
                _record_role("hold_no_first_hop")
            else:
                _record_role(firsthop_category)

        if classify_this_unknown_eoa and not unknown_eoa_behavior_recorded:
            kind, confidence, evidence = _classify_unknown_eoa_non_exchange(
                e=e,
                recipient_norm=recipient_norm,
                end_block=end_block,
                outgoing_all=outgoing_all,
                deposit=deposit,
                dex_router_interaction=dex_router_interaction,
                dex_router_to=dex_router_to,
                dex_router_label=dex_router_label,
                dex_router_tx=dex_router_tx,
            )
            _record_unknown_eoa_behavior(
                kind,
                confidence,
                exit_wei=int(e.amount_wei),
                example={
                    "exit_block": int(e.block_number),
                    "exit_tx": str(e.tx_hash),
                    "recipient": str(e.recipient),
                    "exit_amount": str(_wei_to_token(e.amount_wei)),
                    "first_hop_to": firsthop_to,
                    "first_hop_is_contract": firsthop_is_contract,
                    "evidence": evidence,
                },
            )
            unknown_eoa_behavior_recorded = True

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

    role_exit_amount = {k: str(_wei_to_token(v)) for k, v in role_counter_exit_wei.items()}
    denom_considered = _wei_to_token(considered_exit_wei)
    role_exit_share_percent: Dict[str, str] = {}
    for k, v in role_counter_exit_wei.items():
        amt = _wei_to_token(v)
        role_exit_share_percent[str(k)] = str((amt / denom_considered) * Decimal(100)) if denom_considered > 0 else str(Decimal(0))

    if bool(classify_unknown_eoa_behavior):
        kind_counts: Counter[str] = Counter()
        kind_exit_wei: Dict[str, int] = defaultdict(int)
        for k, c in unknown_eoa_behavior_counts.items():
            kind = str(k).split(":", 1)[0]
            kind_counts[kind] += int(c)
            kind_exit_wei[kind] += int(unknown_eoa_behavior_exit_wei.get(k) or 0)
        unknown_eoa_behavior = {
            "method": "Applies only to exit recipients that are unlabeled EOAs. Classification uses (a) strict labeled-exchange matches (0-3 hops), (b) decoded Arbitrum outboundTransfer() deposits, (c) swap event topics in tx receipts, (d) fallback 'self_custody' when no token outflows are observed.",
            "confidence_buckets": ["high", "medium", "low"],
            "heuristic_max_txs_per_exit": int(heuristic_max_txs_per_exit),
            "dex_swap_topic0_set": sorted(DEX_SWAP_TOPIC0),
            "totals": {
                "unknown_eoa_exit_events": int(unknown_eoa_behavior_total_events),
                "unknown_eoa_exit_amount": str(_wei_to_token(unknown_eoa_behavior_total_exit_wei)),
                "unknown_eoa_exit_amount_wei": int(unknown_eoa_behavior_total_exit_wei),
            },
            "counts_by_kind": dict(kind_counts),
            "exit_amount_by_kind": {k: str(_wei_to_token(v)) for k, v in kind_exit_wei.items()},
            "counts_by_kind_and_confidence": dict(unknown_eoa_behavior_counts),
            "exit_amount_by_kind_and_confidence": {k: str(_wei_to_token(v)) for k, v in unknown_eoa_behavior_exit_wei.items()},
            "examples": unknown_eoa_behavior_examples,
        }

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
            "classify_unknown_eoa_behavior": bool(args.classify_unknown_eoa_behavior),
            "heuristic_max_txs_per_exit": int(heuristic_max_txs_per_exit) if bool(args.classify_unknown_eoa_behavior) else None,
            "arbitrum_followup": {
                "enabled": bool(include_arbitrum_followup),
                "rpc": str(args.arbitrum_rpc) if include_arbitrum_followup else None,
                "l1_gateway_router": str(arb_l1_gateway_router) if include_arbitrum_followup else None,
                "l1_token_gateway": str(arb_l1_token_gateway) if include_arbitrum_followup and arb_l1_token_gateway else None,
                "l2_token_address": str(arb_l2_token_addr) if include_arbitrum_followup and arb_l2_token_addr else None,
                "followup_window_days": int(arbitrum_followup_window_days) if include_arbitrum_followup else None,
                "include_second_hop": bool(args.arbitrum_include_second_hop) if include_arbitrum_followup else None,
            },
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
            "arbitrum_followup": {
                "enabled": bool(include_arbitrum_followup),
                "bridge_deposit_events": int(arb_bridge_deposit_event_count),
                "bridge_deposit_exit_amount": str(_wei_to_token(arb_bridge_deposit_exit_wei)),
                "bridge_deposit_token_amount": str(_wei_to_token(arb_bridge_deposit_token_wei)),
                "matched_to_exchange_events": int(arb_matched_exchange_event_count),
                "matched_to_exchange_exit_amount": str(_wei_to_token(arb_matched_exchange_exit_wei)),
                "matched_to_exchange_token_amount": str(_wei_to_token(arb_matched_exchange_token_wei)),
                "top_exchange_endpoints_by_count": [
                    {"address": str(a), "label": exchange_labels.get(a, {}).get("name"), "count": int(c)}
                    for a, c in arb_exchange_counter.most_common(10)
                ],
                "examples_bridge_deposit": arb_bridge_examples,
                "examples_matched_to_exchange": arb_matched_exchange_examples,
            },
            "post_exit_roles": {
                "method": "Heuristic per-exit categorization: exchange_strict if it reaches a labeled exchange (0-3 hops). Else bridge_deposit if a canonical Arbitrum deposit call is detected. Else dex_router_interaction if a labeled router is the tx.to for a transfer. Else hold/unknown categories.",
                "role_counts": dict(role_counter_events),
                "role_exit_amount": role_exit_amount,
                "role_exit_share_percent": role_exit_share_percent,
                "examples": role_examples,
            },
            "top_exchange_intermediates_by_count": [
                {
                    "address": str(a),
                    "count": int(c),
                    "exit_amount": str(_wei_to_token(exchange_intermediate_exit_wei.get(a) or 0)),
                    "is_contract": exchange_intermediate_is_contract.get(a),
                    "example": exchange_intermediate_example.get(a),
                }
                for a, c in exchange_intermediate_counter.most_common(15)
            ],
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
            "Arbitrum follow-up (when enabled) is best-effort: it only detects deposits via the Arbitrum L1 gateway router outboundTransfer() and only counts transfers into labeled exchanges on Arbitrum.",
        ],
    }

    if unknown_eoa_behavior is not None:
        out["routing_results_top_recipients"]["unknown_eoa_post_exit_heuristics"] = unknown_eoa_behavior

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

    if include_arbitrum_followup:
        lines.append("")
        lines.append("## Arbitrum follow-up (L1 bridge deposit → exchange routing; best-effort)")
        lines.append("")
        lines.append(f"- Arbitrum RPC: `{args.arbitrum_rpc}`")
        lines.append(f"- L1 gateway router: `{arb_l1_gateway_router}`")
        lines.append(f"- L1 token gateway: `{arb_l1_token_gateway}`")
        lines.append(f"- L2 token address: `{arb_l2_token_addr}`")
        lines.append(f"- Follow-up window after deposit: **{int(arbitrum_followup_window_days)} days**")
        lines.append(f"- Exit events with detected Arbitrum deposit: **{arb_bridge_deposit_event_count}**")
        lines.append(
            f"- Exit amount (events) with deposit: **{_format_token(_wei_to_token(arb_bridge_deposit_exit_wei))} {args.token_symbol}**"
        )
        lines.append(
            f"- Bridged token amount (outboundTransfer sum): **{_format_token(_wei_to_token(arb_bridge_deposit_token_wei))} {args.token_symbol}**"
        )
        lines.append(f"- Of those, matched to labeled exchange on Arbitrum (events): **{arb_matched_exchange_event_count}**")
        lines.append(
            f"- Matched exit amount (events): **{_format_token(_wei_to_token(arb_matched_exchange_exit_wei))} {args.token_symbol}**"
        )
        lines.append(
            f"- Matched token amount to exchanges on Arbitrum: **{_format_token(_wei_to_token(arb_matched_exchange_token_wei))} {args.token_symbol}**"
        )
        if arb_exchange_counter:
            lines.append("")
            lines.append("Top exchange endpoints on Arbitrum (by matched count):")
            lines.append("")
            for a, c in arb_exchange_counter.most_common(10):
                label = exchange_labels.get(a, {}).get("name") or a
                lines.append(f"- {label}: **{int(c)}**")

    if role_counter_events:
        lines.append("")
        lines.append("## Post-exit roles (heuristic; top recipients)")
        lines.append("")
        lines.append(
            "These roles are a *best-effort* way to explain what “unknown EOAs / contracts” are doing after exit. They do **not** replace strict exchange routing."
        )
        lines.append("")
        denom = _wei_to_token(considered_exit_wei)
        for role, c in sorted(role_counter_events.items(), key=lambda kv: (-int(kv[1]), str(kv[0]))):
            amt = _wei_to_token(role_counter_exit_wei.get(role) or 0)
            pct = (amt / denom) * Decimal(100) if denom > 0 else Decimal(0)
            lines.append(f"- {role}: **{int(c)}** events; **{_format_token(amt)} {args.token_symbol}** ({pct.quantize(Decimal('0.01'))}%)")

        if exchange_intermediate_counter:
            lines.append("")
            lines.append("Top intermediates on paths that end at labeled exchanges (by count):")
            lines.append("")
            for a, c in exchange_intermediate_counter.most_common(10):
                meta = exchange_intermediate_example.get(a) or {}
                hint = meta.get("example_exchange_label") or meta.get("example_exchange_to") or ""
                lines.append(f"- {a}: **{int(c)}** (example downstream: {hint})")

    if unknown_eoa_behavior is not None:
        totals = unknown_eoa_behavior.get("totals") if isinstance(unknown_eoa_behavior, dict) else {}
        lines.append("")
        lines.append("## Unknown EOA post-exit behavior (heuristic; optional)")
        lines.append("")
        lines.append(
            "This applies only to exit recipients that are **unlabeled EOAs**. It uses strict exchange matches (when enabled), decoded Arbitrum deposits, and swap event topics to bucket behavior; remaining cases fall back to self_custody."
        )
        lines.append("")
        lines.append(f"- Unknown EOA exit events: **{int((totals or {}).get('unknown_eoa_exit_events') or 0)}**")
        lines.append(
            f"- Unknown EOA exit amount: **{_format_token(_wei_to_token(int((totals or {}).get('unknown_eoa_exit_amount_wei') or 0)))} {args.token_symbol}**"
        )
        lines.append("")
        by_kind = unknown_eoa_behavior.get("counts_by_kind") if isinstance(unknown_eoa_behavior, dict) else {}
        by_kind_amt = unknown_eoa_behavior.get("exit_amount_by_kind") if isinstance(unknown_eoa_behavior, dict) else {}
        if isinstance(by_kind, dict):
            for k, c in sorted(by_kind.items(), key=lambda kv: (-int(kv[1]), str(kv[0]))):
                amt = Decimal(str((by_kind_amt or {}).get(k) or "0"))
                lines.append(f"- {k}: **{int(c)}** events; **{_format_token(amt)} {args.token_symbol}**")

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
