#!/usr/bin/env python3
"""
Generate a reproducible, evidence-based report for a Livepeer Treasury proposal on Arbitrum.

Focus:
- Decode the on-chain Governor ProposalCreated event (includes the full Markdown description)
- Decode proposal actions (e.g., ERC20 transfer recipient + amount)
- Locate the executed treasury transfer (ERC20 Transfer logs)

This script is intentionally stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ARBITRUM_PUBLIC_RPC = "https://arb1.arbitrum.io/rpc"

# Livepeer contracts (from https://explorer.livepeer.org/api/contracts)
LIVEPEER_GOVERNOR = "0xcFE4E2879B786C3aa075813F0E364bb5acCb6aa0"
LIVEPEER_TREASURY = "0xf82C1FF415F1fCf582554fDba790E27019c8E8C4"
LPT_TOKEN_ARBITRUM = "0x289ba1701C2F088cf0faf8B3705246331cB8A839"

# Topic0 hashes (cast sig-event ...)
TOPIC0_PROPOSAL_CREATED = "0x7d84a6263ae0d98d3329bd7b46bb4e8d6f98cd35a7adb45c274c8b7fd5ebd5e0"
TOPIC0_ERC20_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ERC20_TRANSFER_SELECTOR = b"\xa9\x05\x9c\xbb"


class RpcError(RuntimeError):
    pass


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 45):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self._id = 0

    def call(self, method: str, params: list) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "livepeer-research/lisar_treasury_proposal_report"},
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
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise RpcError(f"invalid JSON-RPC response: {raw[:200]!r}") from e
        if "error" in data and data["error"] is not None:
            raise RpcError(str(data["error"]))
        return data.get("result")


def _rpc_with_retries(client: RpcClient, method: str, params: list, max_tries: int = 6) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return client.call(method, params)
        except RpcError as e:
            msg = str(e).lower()
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
            if not retryable or attempt == max_tries:
                raise
            time.sleep(min(2 ** (attempt - 1), 20))


def _http_get_json(url: str, timeout_s: int = 30) -> Any:
    req = Request(url, headers={"user-agent": "livepeer-research/lisar_treasury_proposal_report"})
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _pad_topic_address(addr: str) -> str:
    a = addr.lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return "0x" + "0" * 24 + a[2:]


def _topic_to_address(topic: str) -> str:
    if not topic.startswith("0x") or len(topic) != 66:
        raise ValueError(f"unexpected topic: {topic}")
    return "0x" + topic[-40:]


def _hex_to_bytes(data_hex: str) -> bytes:
    if not isinstance(data_hex, str) or not data_hex.startswith("0x"):
        raise ValueError("expected 0x-prefixed hex string")
    return bytes.fromhex(data_hex[2:])


def _read_word(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 32 > len(data):
        raise ValueError("word out of bounds")
    return int.from_bytes(data[offset : offset + 32], byteorder="big")


def _read_address(data: bytes, offset: int) -> str:
    if offset < 0 or offset + 32 > len(data):
        raise ValueError("address out of bounds")
    return "0x" + data[offset + 12 : offset + 32].hex()


def _decode_bytes(data: bytes, offset: int) -> bytes:
    length = _read_word(data, offset)
    start = offset + 32
    end = start + length
    if end > len(data):
        raise ValueError("bytes out of bounds")
    return data[start:end]


def _decode_string(data: bytes, offset: int) -> str:
    raw = _decode_bytes(data, offset)
    return raw.decode("utf-8", errors="replace")


def _decode_address_array(data: bytes, offset: int) -> List[str]:
    length = _read_word(data, offset)
    out = []
    base = offset + 32
    for i in range(length):
        out.append(_read_address(data, base + i * 32))
    return out


def _decode_uint256_array(data: bytes, offset: int) -> List[int]:
    length = _read_word(data, offset)
    out = []
    base = offset + 32
    for i in range(length):
        out.append(_read_word(data, base + i * 32))
    return out


def _decode_bytes_array(data: bytes, offset: int) -> List[bytes]:
    length = _read_word(data, offset)
    head_base = offset + 32
    element_offsets = [_read_word(data, head_base + i * 32) for i in range(length)]
    # Offsets are relative to the start of the offsets section (i.e. right after the length word).
    return [_decode_bytes(data, head_base + o) for o in element_offsets]


def _decode_string_array(data: bytes, offset: int) -> List[str]:
    length = _read_word(data, offset)
    head_base = offset + 32
    element_offsets = [_read_word(data, head_base + i * 32) for i in range(length)]
    # Offsets are relative to the start of the offsets section (i.e. right after the length word).
    return [_decode_string(data, head_base + o) for o in element_offsets]


@dataclass(frozen=True)
class ProposalAction:
    target: str
    value_wei: int
    signature: str
    calldata_hex: str
    decoded: Optional[dict]


def _decode_erc20_transfer_calldata(calldata: bytes) -> Optional[dict]:
    if len(calldata) < 4 + 32 + 32:
        return None
    if calldata[:4] != ERC20_TRANSFER_SELECTOR:
        return None
    to = "0x" + calldata[4 + 12 : 4 + 32].hex()
    amount = int.from_bytes(calldata[4 + 32 : 4 + 64], byteorder="big")
    return {"type": "erc20_transfer", "to": to, "amount": amount}


def _get_block_timestamp(client: RpcClient, block_number: int) -> int:
    block = _rpc_with_retries(client, "eth_getBlockByNumber", [hex(block_number), False])
    if not block:
        raise RpcError(f"missing block {block_number}")
    return int(block["timestamp"], 16)


def _get_logs_range(
    client: RpcClient, *, address: str, topics: list, from_block: int, to_block: int, max_splits: int = 24
) -> List[dict]:
    params = {
        "address": address,
        "topics": topics,
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
    }
    try:
        res = _rpc_with_retries(client, "eth_getLogs", [params])
        return res or []
    except RpcError as e:
        msg = str(e).lower()
        too_many = any(
            s in msg
            for s in (
                "more than",
                "too many results",
                "response size exceeded",
                "query returned more than",
                "block range too wide",
            )
        )
        if not too_many or max_splits <= 0 or from_block >= to_block:
            raise
        mid = (from_block + to_block) // 2
        left = _get_logs_range(
            client, address=address, topics=topics, from_block=from_block, to_block=mid, max_splits=max_splits - 1
        )
        right = _get_logs_range(
            client, address=address, topics=topics, from_block=mid + 1, to_block=to_block, max_splits=max_splits - 1
        )
        return left + right


def _parse_proposal_id(s: str) -> int:
    v = s.strip()
    if v.startswith("0x"):
        return int(v, 16)
    if not re.fullmatch(r"\d+", v):
        raise ValueError(f"invalid proposal id: {s!r}")
    return int(v, 10)


def _to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def decode_proposal_created_event(data_hex: str) -> dict:
    """
    Decode OpenZeppelin Governor ProposalCreated event:
    ProposalCreated(uint256,address,address[],uint256[],string[],bytes[],uint256,uint256,string)
    """
    data = _hex_to_bytes(data_hex)
    if len(data) < 32 * 9:
        raise ValueError("ProposalCreated event data too short")

    proposal_id = _read_word(data, 0)
    proposer = _read_address(data, 32)
    targets_off = _read_word(data, 64)
    values_off = _read_word(data, 96)
    sigs_off = _read_word(data, 128)
    calldatas_off = _read_word(data, 160)
    start = _read_word(data, 192)
    end = _read_word(data, 224)
    desc_off = _read_word(data, 256)

    targets = _decode_address_array(data, targets_off)
    values = _decode_uint256_array(data, values_off)
    signatures = _decode_string_array(data, sigs_off)
    calldatas = _decode_bytes_array(data, calldatas_off)
    description = _decode_string(data, desc_off)

    return {
        "proposal_id": str(proposal_id),
        "proposer": proposer,
        "targets": targets,
        "values": values,
        "signatures": signatures,
        "calldatas": ["0x" + c.hex() for c in calldatas],
        "start": start,
        "end": end,
        "description": description,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--proposal-id",
        required=True,
        help="Proposal id (decimal uint256 as shown in explorer, or 0x hex).",
    )
    parser.add_argument("--rpc-url", default=ARBITRUM_PUBLIC_RPC)
    parser.add_argument("--governor", default=LIVEPEER_GOVERNOR)
    parser.add_argument("--treasury", default=LIVEPEER_TREASURY)
    parser.add_argument("--lpt-token", default=LPT_TOKEN_ARBITRUM)
    parser.add_argument("--from-block", type=int, default=0)
    parser.add_argument("--out-dir", default="artifacts/livepeer-lisar-treasury-proposal")
    args = parser.parse_args()

    proposal_id_int = _parse_proposal_id(args.proposal_id)

    rpc = RpcClient(args.rpc_url)
    latest = int(_rpc_with_retries(rpc, "eth_blockNumber", []), 16)

    proposal_created_logs = _get_logs_range(
        rpc,
        address=args.governor,
        topics=[TOPIC0_PROPOSAL_CREATED],
        from_block=args.from_block,
        to_block=latest,
    )

    decoded = None
    matched_log = None
    for log in proposal_created_logs:
        try:
            d = decode_proposal_created_event(log.get("data") or "0x")
        except ValueError:
            continue
        if int(d["proposal_id"]) == proposal_id_int:
            decoded = d
            matched_log = log
            break

    if decoded is None or matched_log is None:
        raise SystemExit(f"ProposalCreated not found for proposalId={proposal_id_int} in blocks {args.from_block}..{latest}")

    created_block = int(matched_log["blockNumber"], 16)
    created_ts = _get_block_timestamp(rpc, created_block)

    actions: List[ProposalAction] = []
    for i, target in enumerate(decoded["targets"]):
        calldata_hex = decoded["calldatas"][i] if i < len(decoded["calldatas"]) else "0x"
        sig = decoded["signatures"][i] if i < len(decoded["signatures"]) else ""
        value = decoded["values"][i] if i < len(decoded["values"]) else 0
        decoded_action = None
        try:
            decoded_action = _decode_erc20_transfer_calldata(_hex_to_bytes(calldata_hex))
        except ValueError:
            decoded_action = None
        actions.append(
            ProposalAction(
                target=target,
                value_wei=value,
                signature=sig,
                calldata_hex=calldata_hex,
                decoded=decoded_action,
            )
        )

    # If proposal is a treasury LPT transfer, locate the actual Transfer log (Treasury -> recipient).
    treasury_transfer = None
    requested_transfer = next((a for a in actions if a.decoded and a.decoded.get("type") == "erc20_transfer"), None)
    if requested_transfer and requested_transfer.target.lower() == args.lpt_token.lower():
        to_addr = requested_transfer.decoded["to"]
        amount = int(requested_transfer.decoded["amount"])
        transfer_logs = _get_logs_range(
            rpc,
            address=args.lpt_token,
            topics=[TOPIC0_ERC20_TRANSFER, _pad_topic_address(args.treasury), _pad_topic_address(to_addr)],
            from_block=created_block,
            to_block=latest,
            max_splits=12,
        )
        # Choose first matching amount
        for log in transfer_logs:
            if int(log.get("data") or "0x0", 16) != amount:
                continue
            bn = int(log["blockNumber"], 16)
            treasury_transfer = {
                "block_number": bn,
                "block_timestamp": _get_block_timestamp(rpc, bn),
                "tx_hash": log["transactionHash"],
                "from": _topic_to_address(log["topics"][1]),
                "to": _topic_to_address(log["topics"][2]),
                "amount": amount,
            }
            break

    proposal_state = None
    try:
        proposal_state = _http_get_json(
            f"https://explorer.livepeer.org/api/treasury/proposal/{proposal_id_int}/state",
            timeout_s=20,
        )
    except Exception:
        proposal_state = None

    os.makedirs(args.out_dir, exist_ok=True)

    out = {
        "inputs": {
            "proposal_id": str(proposal_id_int),
            "rpc_url": args.rpc_url,
            "governor": args.governor,
            "treasury": args.treasury,
            "lpt_token": args.lpt_token,
            "from_block": args.from_block,
            "to_block": latest,
        },
        "proposal_created": {
            "tx_hash": matched_log.get("transactionHash"),
            "block_number": created_block,
            "block_timestamp": created_ts,
        },
        "proposal": decoded,
        "actions": [
            {
                "target": a.target,
                "value_wei": a.value_wei,
                "signature": a.signature,
                "calldata": a.calldata_hex,
                "decoded": a.decoded,
            }
            for a in actions
        ],
        "treasury_transfer": treasury_transfer,
        "proposal_state": proposal_state,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
    }

    with open(os.path.join(args.out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")

    with open(os.path.join(args.out_dir, "proposal_description.md"), "w", encoding="utf-8") as f:
        f.write(decoded["description"])
        if not decoded["description"].endswith("\n"):
            f.write("\n")

    with open(os.path.join(args.out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("# Livepeer Treasury Proposal — On-Chain Report (Arbitrum)\n\n")
        f.write(f"- Proposal id: `{proposal_id_int}`\n")
        f.write(f"- Governor: `{args.governor}`\n")
        f.write(f"- Created tx: `{matched_log.get('transactionHash')}`\n")
        f.write(f"- Created block: `{created_block}` ({_to_iso(created_ts)})\n")
        f.write(f"- Proposer: `{decoded['proposer']}`\n")
        if proposal_state and isinstance(proposal_state, dict):
            state = proposal_state.get('state')
            if state:
                f.write(f"- Explorer state: `{state}`\n")
        f.write("\n## Actions\n\n")
        for i, a in enumerate(actions):
            f.write(f"### Action {i+1}\n\n")
            f.write(f"- Target: `{a.target}`\n")
            f.write(f"- Value: `{a.value_wei}`\n")
            if a.signature:
                f.write(f"- Signature: `{a.signature}`\n")
            if a.decoded and a.decoded.get("type") == "erc20_transfer":
                f.write(f"- Decoded: `transfer({a.decoded['to']}, {a.decoded['amount']})`\n")
            f.write("\n")

        if treasury_transfer:
            f.write("## Treasury Transfer (ERC20 Transfer Log)\n\n")
            f.write(f"- From: `{treasury_transfer['from']}`\n")
            f.write(f"- To: `{treasury_transfer['to']}`\n")
            f.write(f"- Amount (raw): `{treasury_transfer['amount']}`\n")
            f.write(f"- Tx: `{treasury_transfer['tx_hash']}`\n")
            f.write(
                f"- Block: `{treasury_transfer['block_number']}` ({_to_iso(treasury_transfer['block_timestamp'])})\n"
            )
            f.write("\n")

        f.write("## Proposal Description\n\n")
        f.write("See `proposal_description.md`.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
