#!/usr/bin/env python3
"""
Decode Arbitrum LPT "bridge-out" transactions to Ethereum L1.

Motivation
----------
In the Arbitrum delegation outflows research we observed many large withdrawers
immediately "burn" LPT on Arbitrum by calling the Arbitrum gateway router,
which emits `Transfer(from=wallet, to=0x0000..., amount)` on the Arbitrum LPT
token contract.

Those transactions are not an in-place "sell" that Arbitrum buyers absorb; they
are typically a bridge-out to Ethereum L1. The first step to answering "who
absorbs whale selling" is decoding the bridge-outs to find the L1 recipients.

This tool:
- Finds Arbitrum LPT burn events (`Transfer` to the zero address) for top
  withdrawers.
- Fetches the underlying Arbitrum tx and decodes the call data.
- Summarizes the L1 recipient addresses (`to`) and amounts.

Stdlib-only; uses JSON-RPC via urllib.

Selector evidence (4byte): `0x7b3a3c8b` == `outboundTransfer(address,address,uint256,bytes)`.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

ARBITRUM_RPC_DEFAULT = "https://arb1.arbitrum.io/rpc"
ETHEREUM_MAINNET_RPC_DEFAULT = "https://rpc.flashbots.net"

# Arbitrum LPT token (from previous workspace scans)
LPT_TOKEN_ARB = "0x289ba1701c2f088cf0faf8b3705246331cb8a839"
# Arbitrum L2GatewayRouter (seen in burn txs)
ARB_L2_GATEWAY_ROUTER = "0x5288c571fd7ad117bea99bf60fe0846c4e84f933"

LPT_TOKEN_L1 = "0x58b6a8a3302369daec383334672404ee733ab239"

TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TOPIC0_TRANSFER_ROUTED = "0x85291dff2161a93c2f12c819d31889c96c63042116f5bc5a205aa701c2c429f5"  # TransferRouted(address,address,address,address)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

SELECTOR_OUTBOUND_TRANSFER = "0x7b3a3c8b"  # outboundTransfer(address,address,uint256,bytes)

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS


class RpcError(RuntimeError):
    pass


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 60):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s

    def call_raw(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "livepeer-research/arb-bridge-out-decode"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except HTTPError as e:
            raise RpcError(f"HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            raise RpcError(f"URL error: {e.reason}") from e
        except Exception as e:
            raise RpcError(f"RPC transport error: {e}") from e
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise RpcError(f"invalid JSON-RPC response: {raw[:200]!r}") from e

    def call(self, method: str, params: List[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        resp = self.call_raw(payload)
        if isinstance(resp, dict) and resp.get("error"):
            raise RpcError(str(resp["error"]))
        return resp.get("result")


def _rpc_with_retries(fn, *, max_tries: int = 8) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return fn()
        except RpcError as e:
            msg = str(e).lower()
            retryable = any(
                s in msg for s in ("timeout", "timed out", "too many requests", "rate limit", "service unavailable", "bad gateway")
            )
            if not retryable or attempt == max_tries:
                raise
            time.sleep(min(2 ** (attempt - 1), 20))


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _pad_topic_address(addr: str) -> str:
    a = _normalize_address(addr)
    return "0x" + ("0" * 24) + a[2:]


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _decode_uint256(data_hex: str) -> int:
    if not data_hex.startswith("0x"):
        raise ValueError("hex must be 0x-prefixed")
    return int(data_hex, 16)


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
    selector = "0x" + calldata_hex[2:10]
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

    token = "0x" + token_word[-40:]
    to = "0x" + to_word[-40:]
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
        "token": _normalize_address(token),
        "to": _normalize_address(to),
        "amount": amount,
        "data": data,
    }


def _decode_transfer_routed_log(log: Dict[str, Any]) -> Dict[str, str]:
    topics = [str(t).lower() for t in (log.get("topics") or [])]
    if len(topics) != 4 or topics[0] != TOPIC0_TRANSFER_ROUTED:
        raise ValueError("not a TransferRouted log")

    def topic_addr(t: str) -> str:
        if not t.startswith("0x") or len(t) != 66:
            raise ValueError("invalid topic")
        return _normalize_address("0x" + t[-40:])

    token = topic_addr(topics[1])
    from_addr = topic_addr(topics[2])
    to_addr = topic_addr(topics[3])
    data = str(log.get("data") or "").lower()
    if not data.startswith("0x") or len(data) != 66:
        raise ValueError("invalid data")
    gateway = _normalize_address("0x" + data[-40:])

    return {"token": token, "from": from_addr, "to": to_addr, "gateway": gateway}


def _is_chunkable_logs_error(err_msg: str) -> bool:
    msg = err_msg.lower()
    return any(s in msg for s in ("block range", "too large", "query returned more than", "response size", "log response size"))


def _get_logs_with_chunking(
    rpc: RpcClient,
    *,
    address: str,
    topics: List[Optional[str]],
    from_block: int,
    to_block: int,
    chunk_size: int,
) -> List[Dict[str, Any]]:
    def get_one(start: int, end: int) -> List[Dict[str, Any]]:
        params = [
            {
                "address": address,
                "fromBlock": hex(int(start)),
                "toBlock": hex(int(end)),
                "topics": topics,
            }
        ]
        return _rpc_with_retries(lambda: rpc.call("eth_getLogs", params))

    # Fast path: try single range.
    try:
        return get_one(from_block, to_block)
    except RpcError as e:
        if not _is_chunkable_logs_error(str(e)):
            raise

    # Fallback: chunk / bisect.
    out: List[Dict[str, Any]] = []
    stack: List[Tuple[int, int]] = [(int(from_block), int(to_block))]
    cs = max(int(chunk_size), 1)

    while stack:
        start, end = stack.pop()
        if start > end:
            continue
        if (end - start + 1) <= cs:
            try:
                out.extend(get_one(start, end))
                continue
            except RpcError as e:
                if start == end or not _is_chunkable_logs_error(str(e)):
                    raise
                mid = (start + end) // 2
                stack.append((start, mid))
                stack.append((mid + 1, end))
                continue

        # Split into chunk-sized windows.
        for s in range(start, end + 1, cs):
            stack.append((s, min(end, s + cs - 1)))

    return out


@dataclass(frozen=True)
class DecodedBridgeOut:
    arb_tx_hash: str
    arb_block: int
    arb_ts: int
    arb_date_utc: str
    arb_tx_from: str
    arb_tx_to: str
    from_addr: str
    l2_router: str
    selector: str
    l1_token: str
    l1_to: str
    amount_wei: int
    amount_lpt: str
    burn_log_amount_wei: int
    call_amount_wei: Optional[int]
    burn_matches_call_amount: Optional[bool]
    routed_gateway: Optional[str]
    decode_source: str
    data_hex: str
    data_len_bytes: int


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arb-rpc-url", default=ARBITRUM_RPC_DEFAULT)
    parser.add_argument("--eth-rpc-url", default=ETHEREUM_MAINNET_RPC_DEFAULT, help="Used only for eth_getCode classification.")
    parser.add_argument(
        "--burn-daterange-json",
        default=os.path.join("..", "..", "artifacts", "livepeer-delegator-flows", "top_withdrawers_burn_to_zero_daterange.json"),
        help="Workspace artifact: burn date ranges for the biggest withdrawers.",
    )
    parser.add_argument("--lpt-arb", default=LPT_TOKEN_ARB)
    parser.add_argument("--l2-router", default=ARB_L2_GATEWAY_ROUTER)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--chunk-size", type=int, default=5_000_000, help="Fallback chunk size for eth_getLogs.")
    parser.add_argument("--out-md", default="research/arbitrum-bridge-out-decode.md")
    parser.add_argument("--out-json", default="research/arbitrum-bridge-out-decode.json")
    args = parser.parse_args()

    arb_rpc = RpcClient(args.arb_rpc_url)
    eth_rpc = RpcClient(args.eth_rpc_url) if args.eth_rpc_url else None

    burn_payload = _read_json(args.burn_daterange_json)
    if isinstance(burn_payload, dict) and isinstance(burn_payload.get("rows"), list):
        burn_rows = burn_payload["rows"]
    elif isinstance(burn_payload, list):
        burn_rows = burn_payload
    else:
        raise SystemExit(f"unexpected burn daterange json shape: {args.burn_daterange_json}")

    rows = [r for r in burn_rows if float(r.get("burn_total_lpt", 0.0)) > 0]
    rows.sort(key=lambda r: float(r.get("burn_total_lpt", 0.0)), reverse=True)
    rows = rows[: max(0, int(args.top_n))]

    lpt_arb = _normalize_address(args.lpt_arb)
    l2_router = _normalize_address(args.l2_router)

    block_ts_cache: Dict[int, int] = {}

    def get_block_ts(block_number: int) -> int:
        if block_number in block_ts_cache:
            return block_ts_cache[block_number]
        blk = _rpc_with_retries(lambda: arb_rpc.call("eth_getBlockByNumber", [hex(block_number), False]))
        ts = int(blk["timestamp"], 16)
        block_ts_cache[block_number] = ts
        return ts

    decoded: List[DecodedBridgeOut] = []

    for r in rows:
        sender = _normalize_address(r["address"])
        from_block = int(r["burn_first_block"])
        to_block = int(r["burn_last_block"])

        topics = [TOPIC0_TRANSFER, _pad_topic_address(sender), _pad_topic_address(ZERO_ADDRESS)]
        logs = _get_logs_with_chunking(
            arb_rpc,
            address=lpt_arb,
            topics=topics,
            from_block=from_block,
            to_block=to_block,
            chunk_size=int(args.chunk_size),
        )

        for log in logs:
            tx_hash = str(log["transactionHash"]).lower()
            block_number = int(str(log["blockNumber"]), 16)
            burn_amount_wei = _decode_uint256(str(log["data"]))

            tx = _rpc_with_retries(lambda: arb_rpc.call("eth_getTransactionByHash", [tx_hash]))
            tx_from = (tx.get("from") or "").lower()
            tx_to = (tx.get("to") or "").lower()
            tx_input = (tx.get("input") or "").lower()
            if not tx_to or not tx_from:
                continue

            receipt = _rpc_with_retries(lambda: arb_rpc.call("eth_getTransactionReceipt", [tx_hash]))
            router_logs = [
                l
                for l in (receipt.get("logs") or [])
                if str(l.get("address") or "").lower() == l2_router
                and (l.get("topics") or [])
                and str((l.get("topics") or [None])[0]).lower() == TOPIC0_TRANSFER_ROUTED
            ]

            routed: Optional[Dict[str, str]] = None
            for rl in router_logs:
                try:
                    cand = _decode_transfer_routed_log(rl)
                except Exception:
                    continue
                if cand["from"] == sender:
                    routed = cand
                    break

            call_amount_wei: Optional[int] = None
            call_matches_burn: Optional[bool] = None
            data_hex = "0x"
            data_len_bytes = 0
            selector = SELECTOR_OUTBOUND_TRANSFER
            decode_source = "transferRouted"

            if routed is None:
                # Fallback: direct router call with ABI-decodable calldata.
                if tx_to != l2_router or not tx_input.startswith(SELECTOR_OUTBOUND_TRANSFER):
                    continue
                dec = _decode_outbound_transfer(tx_input)
                routed = {"token": dec["token"], "from": sender, "to": dec["to"], "gateway": ""}
                call_amount_wei = int(dec["amount"])
                call_matches_burn = call_amount_wei == burn_amount_wei
                data_hex = str(dec["data"])
                data_len_bytes = (len(data_hex) - 2) // 2 if data_hex.startswith("0x") else 0
                selector = dec["selector"]
                decode_source = "calldata"
            else:
                # Best-effort: if tx.to is the router, decode calldata for amount/data cross-checks.
                if tx_to == l2_router and tx_input.startswith(SELECTOR_OUTBOUND_TRANSFER):
                    try:
                        dec = _decode_outbound_transfer(tx_input)
                        call_amount_wei = int(dec["amount"])
                        call_matches_burn = call_amount_wei == burn_amount_wei
                        data_hex = str(dec["data"])
                        data_len_bytes = (len(data_hex) - 2) // 2 if data_hex.startswith("0x") else 0
                        selector = dec["selector"]
                    except Exception:
                        pass

            ts = get_block_ts(block_number)
            decoded.append(
                DecodedBridgeOut(
                    arb_tx_hash=tx_hash,
                    arb_block=block_number,
                    arb_ts=ts,
                    arb_date_utc=_iso(ts)[:10],
                    arb_tx_from=_normalize_address(tx_from),
                    arb_tx_to=_normalize_address(tx_to),
                    from_addr=sender,
                    l2_router=l2_router,
                    selector=selector,
                    l1_token=routed["token"],
                    l1_to=routed["to"],
                    amount_wei=burn_amount_wei,
                    amount_lpt=str(_wei_to_lpt(burn_amount_wei)),
                    burn_log_amount_wei=burn_amount_wei,
                    call_amount_wei=call_amount_wei,
                    burn_matches_call_amount=call_matches_burn,
                    routed_gateway=routed.get("gateway"),
                    decode_source=decode_source,
                    data_hex=data_hex,
                    data_len_bytes=data_len_bytes,
                )
            )

    # L1 recipient classification (EOA vs contract), optional.
    recipient_type_l1: Dict[str, str] = {}
    if eth_rpc is not None and decoded:
        for a in sorted({t.l1_to for t in decoded}):
            code = _rpc_with_retries(lambda: eth_rpc.call("eth_getCode", [a, "latest"]))
            recipient_type_l1[a] = "contract" if isinstance(code, str) and code not in ("0x", "0x0") and len(code) > 2 else "eoa"

    # Summaries.
    per_sender: Dict[str, Dict[str, Any]] = {}
    overall_by_recipient: Dict[str, Decimal] = defaultdict(Decimal)
    overall_total = Decimal(0)

    for t in decoded:
        amt = Decimal(t.amount_lpt)
        overall_total += amt
        overall_by_recipient[t.l1_to] += amt

        s = per_sender.get(t.from_addr)
        if s is None:
            s = {
                "from": t.from_addr,
                "burn_txs": 0,
                "burn_total_lpt": Decimal(0),
                "recipients": set(),
                "to_amounts": defaultdict(Decimal),
                "self_recipient_lpt": Decimal(0),
                "l1_token_mismatch": 0,
                "amount_mismatch": 0,
            }
            per_sender[t.from_addr] = s

        s["burn_txs"] += 1
        s["burn_total_lpt"] += amt
        s["recipients"].add(t.l1_to)
        s["to_amounts"][t.l1_to] += amt
        if t.l1_to == t.from_addr:
            s["self_recipient_lpt"] += amt
        if t.l1_token != LPT_TOKEN_L1:
            s["l1_token_mismatch"] += 1
        if t.burn_matches_call_amount is False:
            s["amount_mismatch"] += 1

    senders_json: List[Dict[str, Any]] = []
    for sender, s in sorted(per_sender.items(), key=lambda kv: kv[1]["burn_total_lpt"], reverse=True):
        burn_total = s["burn_total_lpt"]
        senders_json.append(
            {
                "from": sender,
                "burn_txs": int(s["burn_txs"]),
                "burn_total_lpt": float(burn_total),
                "unique_recipients": sorted(list(s["recipients"])),
                "self_recipient_lpt": float(s["self_recipient_lpt"]),
                "self_recipient_share": float(s["self_recipient_lpt"] / burn_total) if burn_total > 0 else 0.0,
                "l1_token_mismatch_txs": int(s["l1_token_mismatch"]),
                "amount_mismatch_txs": int(s["amount_mismatch"]),
                "top_recipients": [
                    {
                        "to": to,
                        "recipient_type_l1": recipient_type_l1.get(to),
                        "total_lpt": float(amt),
                        "share_of_sender": float(amt / burn_total) if burn_total > 0 else 0.0,
                    }
                    for to, amt in sorted(dict(s["to_amounts"]).items(), key=lambda kv: kv[1], reverse=True)[:10]
                ],
            }
        )

    overall_top = [
        {
            "to": to,
            "recipient_type_l1": recipient_type_l1.get(to),
            "total_lpt": float(amt),
            "share_of_overall": float(amt / overall_total) if overall_total > 0 else 0.0,
        }
        for to, amt in sorted(overall_by_recipient.items(), key=lambda kv: kv[1], reverse=True)[:25]
    ]

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "arb_rpc_url": args.arb_rpc_url,
            "eth_rpc_url": args.eth_rpc_url,
            "burn_daterange_json": args.burn_daterange_json,
            "lpt_token_arb": lpt_arb,
            "l2_gateway_router": l2_router,
            "selector": SELECTOR_OUTBOUND_TRANSFER,
            "selector_text": "outboundTransfer(address,address,uint256,bytes)",
            "top_n_withdrawers": int(args.top_n),
        },
        "totals": {
            "decoded_burn_txs": len(decoded),
            "unique_l1_recipients": len(overall_by_recipient),
            "decoded_total_lpt": float(overall_total),
        },
        "senders": senders_json,
        "overall_top_recipients": overall_top,
        "recipient_type_l1": recipient_type_l1,
        "decoded_txs": [
            {
                "arb_tx_hash": t.arb_tx_hash,
                "arb_block": t.arb_block,
                "arb_date_utc": t.arb_date_utc,
                "from": t.from_addr,
                "l2_router": t.l2_router,
                "selector": t.selector,
                "l1_token": t.l1_token,
                "l1_to": t.l1_to,
                "amount_wei": str(t.amount_wei),
                "amount_lpt": t.amount_lpt,
                "burn_log_amount_wei": str(t.burn_log_amount_wei),
                "call_amount_wei": str(t.call_amount_wei) if t.call_amount_wei is not None else None,
                "burn_matches_call_amount": t.burn_matches_call_amount,
                "routed_gateway": t.routed_gateway,
                "decode_source": t.decode_source,
                "data_len_bytes": int(t.data_len_bytes),
                "data_hex": t.data_hex,
            }
            for t in sorted(decoded, key=lambda x: (x.arb_block, x.arb_tx_hash))
        ],
    }

    _write_json_atomic(args.out_json, out_json)

    # Markdown report.
    lines: List[str] = []
    lines.append("# Livepeer Arbitrum → Ethereum L1 — Bridge-out decode (LPT)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- Arbitrum RPC: `{args.arb_rpc_url}`")
    lines.append(f"- Ethereum RPC (for code checks): `{args.eth_rpc_url}`")
    lines.append(f"- LPT (Arbitrum): `{lpt_arb}`")
    lines.append(f"- Gateway router (Arbitrum): `{l2_router}`")
    lines.append("")
    lines.append("This report decodes calls with selector:")
    lines.append(f"- `{SELECTOR_OUTBOUND_TRANSFER}` = `outboundTransfer(address,address,uint256,bytes)`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Decoded burn txs: **{out_json['totals']['decoded_burn_txs']}**")
    lines.append(f"- Unique L1 recipients: **{out_json['totals']['unique_l1_recipients']}**")
    lines.append(f"- Total bridged (decoded): **{_format_lpt(Decimal(str(out_json['totals']['decoded_total_lpt'])))} LPT**")
    lines.append("")
    lines.append("## Top L1 recipients (overall)")
    lines.append("")
    lines.append("| Rank | Recipient (L1) | Type | Total LPT | Share |")
    lines.append("|---:|---|---|---:|---:|")
    for i, row in enumerate(out_json["overall_top_recipients"], start=1):
        lines.append(
            f"| {i} | `{row['to']}` | {row.get('recipient_type_l1') or ''} | {_format_lpt(Decimal(str(row['total_lpt'])))} | {row['share_of_overall']*100:.2f}% |"
        )
    lines.append("")
    lines.append("## Per whale (top withdrawers by burn total)")
    lines.append("")
    for s in out_json["senders"]:
        lines.append(f"### `{s['from']}`")
        lines.append("")
        lines.append(f"- Burn txs decoded: **{s['burn_txs']}**")
        lines.append(f"- Bridged total: **{_format_lpt(Decimal(str(s['burn_total_lpt'])))} LPT**")
        lines.append(f"- Unique L1 recipients: **{len(s['unique_recipients'])}**")
        lines.append(f"- Self-recipient share: **{s['self_recipient_share']*100:.2f}%**")
        if s.get("l1_token_mismatch_txs"):
            lines.append(f"- WARNING: L1 token mismatch txs: **{s['l1_token_mismatch_txs']}** (expected `{LPT_TOKEN_L1}`)")
        if s.get("amount_mismatch_txs"):
            lines.append(f"- WARNING: burn amount mismatch txs: **{s['amount_mismatch_txs']}**")
        lines.append("")
        lines.append("| Rank | Recipient (L1) | Type | Total LPT | Share of sender |")
        lines.append("|---:|---|---|---:|---:|")
        for i, row in enumerate(s["top_recipients"], start=1):
            lines.append(
                f"| {i} | `{row['to']}` | {row.get('recipient_type_l1') or ''} | {_format_lpt(Decimal(str(row['total_lpt'])))} | {row['share_of_sender']*100:.2f}% |"
            )
        lines.append("")

    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
