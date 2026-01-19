#!/usr/bin/env python3
"""
Trace a wallet's Livepeer stake origin on Ethereum L1.

Outputs:
- JSON: machine-readable evidence (tx hashes, totals)
- Markdown: human summary

Stdlib-only; uses JSON-RPC (default: Flashbots).
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

ETHEREUM_MAINNET_RPC_DEFAULT = "https://rpc.flashbots.net"

LPT_TOKEN_L1 = "0x58b6a8a3302369daec383334672404ee733ab239"
LIVEPEER_BONDING_MANAGER_L1 = "0x511bc4556d823ae99630ae8de28b9b80df90ea2e"

TOPIC0 = {
    # cast sig-event "Transfer(address,address,uint256)"
    "ERC20_Transfer": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
    # Livepeer BondingManager events (same as the Arbitrum scan)
    "Bond": "0xe5917769f276ddca9f2ee7c6b0b33e1d1e1b61008010ce622c632dd20d168a23",
    "Unbond": "0x2d5d98d189bee5496a08db2a5948cb7e5e786f09d17d0c3f228eb41776c24a06",
    "WithdrawStake": "0x1340f1a8f3d456a649e1a12071dfa15655e3d09252131d0f980c3b405cc8dd2e",
    "EarningsClaimed": "0xd7eab0765b772ea6ea859d5633baf737502198012e930f257f90013d9b211094",
}

# getDelegator(address) selector: 0xa64ad595
GET_DELEGATOR_SELECTOR = "a64ad595"

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS
ETH_DECIMALS = 18
ETH_SCALE = Decimal(10) ** ETH_DECIMALS


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
            headers={"content-type": "application/json", "user-agent": "livepeer-research/eth-l1-wallet-origin"},
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


def _wei_to_eth(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / ETH_SCALE


def _format_decimal(x: Decimal, *, places: int) -> str:
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


def _eth_block_number(rpc: RpcClient) -> int:
    resp = _rpc_with_retries(lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}))
    if not isinstance(resp, dict) or not isinstance(resp.get("result"), str):
        raise RpcError(f"unexpected eth_blockNumber response: {resp!r}")
    return int(resp["result"], 16)


def _eth_get_block_ts(rpc: RpcClient, *, block_number: int, cache: Dict[int, int]) -> int:
    if block_number in cache:
        return cache[block_number]
    resp = _rpc_with_retries(
        lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber", "params": [hex(block_number), False]})
    )
    if not isinstance(resp, dict) or not isinstance(resp.get("result"), dict):
        raise RpcError(f"unexpected eth_getBlockByNumber response: {resp!r}")
    ts = int(resp["result"]["timestamp"], 16)
    cache[block_number] = ts
    return ts


def _eth_get_code(rpc: RpcClient, *, addr: str, block_tag: str) -> str:
    a = _normalize_address(addr)
    resp = _rpc_with_retries(lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 3, "method": "eth_getCode", "params": [a, block_tag]}))
    if not isinstance(resp, dict) or not isinstance(resp.get("result"), str):
        raise RpcError(f"unexpected eth_getCode response: {resp!r}")
    return resp["result"]


def _eth_get_logs(rpc: RpcClient, *, params: Dict[str, Any]) -> List[dict]:
    resp = _rpc_with_retries(lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 4, "method": "eth_getLogs", "params": [params]}))
    if not isinstance(resp, dict):
        raise RpcError(f"unexpected eth_getLogs response type: {type(resp)}")
    if resp.get("error"):
        raise RpcError(str(resp["error"]))
    out = resp.get("result") or []
    if not isinstance(out, list):
        raise RpcError(f"unexpected eth_getLogs result type: {type(out)}")
    return out


def _eth_get_transaction_receipt(rpc: RpcClient, *, tx_hash: str) -> dict:
    resp = _rpc_with_retries(
        lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 5, "method": "eth_getTransactionReceipt", "params": [tx_hash]})
    )
    if not isinstance(resp, dict) or not isinstance(resp.get("result"), dict):
        raise RpcError(f"unexpected eth_getTransactionReceipt response: {resp!r}")
    return resp["result"]


def _call_data_get_delegator(addr: str) -> str:
    a = _normalize_address(addr)
    return "0x" + GET_DELEGATOR_SELECTOR + ("0" * 24) + a[2:]


def _parse_get_delegator_output(out: str) -> Tuple[int, str]:
    if not isinstance(out, str) or not out.startswith("0x"):
        raise ValueError("invalid eth_call output")
    hex_data = out[2:]
    if len(hex_data) < 64 * 3:
        raise ValueError("short getDelegator output")
    bonded_amount = int(hex_data[0:64], 16)
    delegate_slot = hex_data[128:192]
    delegate_addr = "0x" + delegate_slot[24:64]
    return bonded_amount, delegate_addr.lower()


def _eth_call_get_delegator(rpc: RpcClient, *, bonding_manager: str, delegator: str, block_tag: str) -> Tuple[int, str]:
    call_obj = {"to": bonding_manager, "data": _call_data_get_delegator(delegator)}
    resp = _rpc_with_retries(lambda: rpc.call_raw({"jsonrpc": "2.0", "id": 6, "method": "eth_call", "params": [call_obj, block_tag]}))
    if not isinstance(resp, dict) or not isinstance(resp.get("result"), str):
        raise RpcError(f"unexpected eth_call response: {resp!r}")
    return _parse_get_delegator_output(resp["result"])


@dataclass(frozen=True)
class BondEvent:
    block_number: int
    tx_hash: str
    new_delegate: str
    old_delegate: str
    additional_wei: int
    bonded_wei: int


def _load_bond_events(rpc: RpcClient, *, bonding_manager: str, delegator: str, from_block: int, to_block: int) -> List[BondEvent]:
    logs = _eth_get_logs(
        rpc,
        params={
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": bonding_manager,
            "topics": [TOPIC0["Bond"], None, None, _pad_topic_address(delegator)],
        },
    )
    out: List[BondEvent] = []
    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 4:
            continue
        bn = int(log["blockNumber"], 16)
        tx_hash = str(log.get("transactionHash"))
        new_delegate = ("0x" + topics[1][-40:]).lower()
        old_delegate = ("0x" + topics[2][-40:]).lower()
        additional, bonded = _decode_words(str(log.get("data") or "0x"), 2)
        out.append(
            BondEvent(
                block_number=bn,
                tx_hash=tx_hash,
                new_delegate=new_delegate,
                old_delegate=old_delegate,
                additional_wei=int(additional),
                bonded_wei=int(bonded),
            )
        )
    out.sort(key=lambda e: (e.block_number, e.tx_hash))
    return out


def _load_lifecycle_totals(
    rpc: RpcClient, *, bonding_manager: str, delegator: str, from_block: int, to_block: int
) -> Dict[str, Any]:
    t = _pad_topic_address(delegator)

    unbond_logs = _eth_get_logs(
        rpc,
        params={
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": bonding_manager,
            "topics": [TOPIC0["Unbond"], None, t],
        },
    )
    unbond_total = 0
    for log in unbond_logs:
        _lock_id, amount, _withdraw_round = _decode_words(str(log.get("data") or "0x"), 3)
        unbond_total += int(amount)

    withdraw_logs = _eth_get_logs(
        rpc,
        params={
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": bonding_manager,
            "topics": [TOPIC0["WithdrawStake"], t],
        },
    )
    withdraw_total = 0
    for log in withdraw_logs:
        _lock_id, amount = _decode_words(str(log.get("data") or "0x"), 2)
        withdraw_total += int(amount)

    claim_logs = _eth_get_logs(
        rpc,
        params={
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": bonding_manager,
            "topics": [TOPIC0["EarningsClaimed"], None, t],
        },
    )
    rewards_total = 0
    fees_total = 0
    for log in claim_logs:
        rewards, fees, _start_round, _end_round = _decode_words(str(log.get("data") or "0x"), 4)
        rewards_total += int(rewards)
        fees_total += int(fees)

    return {
        "unbond_events": len(unbond_logs),
        "unbond_total_lpt": str(_wei_to_lpt(unbond_total)),
        "withdraw_events": len(withdraw_logs),
        "withdraw_total_lpt": str(_wei_to_lpt(withdraw_total)),
        "claim_events": len(claim_logs),
        "rewards_claimed_total_lpt": str(_wei_to_lpt(rewards_total)),
        "fees_claimed_total_eth": str(_wei_to_eth(fees_total)),
    }


def _load_lpt_transfers(rpc: RpcClient, *, token: str, wallet: str, from_block: int, to_block: int) -> Tuple[List[dict], List[dict]]:
    wallet_topic = _pad_topic_address(wallet)
    in_logs = _eth_get_logs(
        rpc,
        params={
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": token,
            "topics": [TOPIC0["ERC20_Transfer"], None, wallet_topic],
        },
    )
    out_logs = _eth_get_logs(
        rpc,
        params={
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": token,
            "topics": [TOPIC0["ERC20_Transfer"], wallet_topic],
        },
    )
    return in_logs, out_logs


def _summarize_transfers(*, wallet: str, in_logs: List[dict], out_logs: List[dict]) -> Dict[str, Any]:
    in_total = 0
    out_total = 0
    in_by_sender: Dict[str, int] = defaultdict(int)
    out_by_recipient: Dict[str, int] = defaultdict(int)

    for log in in_logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        sender = ("0x" + topics[1][-40:]).lower()
        amt = int(str(log.get("data") or "0x"), 16)
        in_total += amt
        in_by_sender[sender] += amt

    for log in out_logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        recipient = ("0x" + topics[2][-40:]).lower()
        amt = int(str(log.get("data") or "0x"), 16)
        out_total += amt
        out_by_recipient[recipient] += amt

    top_in = [
        {"from": a, "lpt": str(_wei_to_lpt(v))}
        for a, v in sorted(in_by_sender.items(), key=lambda kv: kv[1], reverse=True)[:20]
    ]
    top_out = [
        {"to": a, "lpt": str(_wei_to_lpt(v))}
        for a, v in sorted(out_by_recipient.items(), key=lambda kv: kv[1], reverse=True)[:20]
    ]

    return {
        "wallet": wallet,
        "inbound_transfers": len(in_logs),
        "outbound_transfers": len(out_logs),
        "unique_senders": len(in_by_sender),
        "unique_recipients": len(out_by_recipient),
        "in_total_lpt": str(_wei_to_lpt(in_total)),
        "out_total_lpt": str(_wei_to_lpt(out_total)),
        "net_lpt": str(_wei_to_lpt(in_total - out_total)),
        "top_inbound_senders": top_in,
        "top_outbound_recipients": top_out,
    }


def _identify_bond_deposit_destinations(
    rpc: RpcClient,
    *,
    token: str,
    wallet: str,
    bond_events: List[BondEvent],
) -> Dict[str, Any]:
    transfer_topic0 = TOPIC0["ERC20_Transfer"].lower()
    wallet_topic = _pad_topic_address(wallet).lower()
    token = token.lower()

    dest_totals: Dict[str, int] = defaultdict(int)
    evidence: List[Dict[str, Any]] = []
    token_out_logs_by_block: Dict[int, List[dict]] = {}

    for ev in bond_events:
        if ev.additional_wei <= 0:
            continue

        if ev.block_number not in token_out_logs_by_block:
            token_out_logs_by_block[ev.block_number] = _eth_get_logs(
                rpc,
                params={
                    "fromBlock": hex(ev.block_number),
                    "toBlock": hex(ev.block_number),
                    "address": token,
                    "topics": [transfer_topic0, wallet_topic],
                },
            )
        logs = token_out_logs_by_block[ev.block_number]

        matched_to: Optional[str] = None
        for log in logs:
            if str(log.get("transactionHash", "")).lower() != ev.tx_hash.lower():
                continue
            topics = [str(t).lower() for t in (log.get("topics") or [])]
            if len(topics) < 3:
                continue
            if topics[0] != transfer_topic0:
                continue
            if topics[1] != wallet_topic:
                continue
            amount = int(str(log.get("data") or "0x"), 16)
            if amount != ev.additional_wei:
                continue
            matched_to = ("0x" + topics[2][-40:]).lower()
            dest_totals[matched_to] += amount
            break

        evidence.append(
            {
                "bond_block_number": ev.block_number,
                "bond_tx_hash": ev.tx_hash,
                "bond_new_delegate": ev.new_delegate,
                "bond_additional_lpt": str(_wei_to_lpt(ev.additional_wei)),
                "transfer_to": matched_to,
            }
        )

    ranked = [
        {"to": a, "bond_deposit_total_lpt": str(_wei_to_lpt(v))}
        for a, v in sorted(dest_totals.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return {"deposit_destinations": ranked, "evidence": evidence}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True, help="Ethereum address (0x...)")
    parser.add_argument("--rpc-url", default=os.environ.get("ETH_RPC_URL", ETHEREUM_MAINNET_RPC_DEFAULT))
    parser.add_argument("--lpt-token", default=LPT_TOKEN_L1)
    parser.add_argument("--bonding-manager", default=LIVEPEER_BONDING_MANAGER_L1)
    parser.add_argument("--from-block", type=int, default=0)
    parser.add_argument("--to-block", type=int, default=0, help="0 = latest")
    parser.add_argument("--block-lag", type=int, default=5)
    parser.add_argument("--out-md", default=None)
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args()

    wallet = _normalize_address(args.wallet)
    token = _normalize_address(args.lpt_token)
    bonding_manager = _normalize_address(args.bonding_manager)
    from_block = max(0, int(args.from_block))

    rpc = RpcClient(args.rpc_url)

    latest_block = _eth_block_number(rpc)
    to_block = int(args.to_block) if int(args.to_block) > 0 else latest_block
    snapshot_block = max(from_block, to_block - max(0, int(args.block_lag)))
    block_tag = hex(snapshot_block)

    slug = wallet[2:10]
    out_md = args.out_md or f"research/eth-l1-wallet-{slug}-origin.md"
    out_json = args.out_json or f"research/eth-l1-wallet-{slug}-origin.json"

    ts_cache: Dict[int, int] = {}
    snapshot_ts = _eth_get_block_ts(rpc, block_number=snapshot_block, cache=ts_cache)

    code = _eth_get_code(rpc, addr=wallet, block_tag=block_tag)
    is_contract = code != "0x"

    bonded_now_wei, delegate_now = _eth_call_get_delegator(rpc, bonding_manager=bonding_manager, delegator=wallet, block_tag=block_tag)

    bond_events = _load_bond_events(rpc, bonding_manager=bonding_manager, delegator=wallet, from_block=from_block, to_block=snapshot_block)
    total_additional = sum(e.additional_wei for e in bond_events)
    max_bonded = max((e.bonded_wei for e in bond_events), default=0)
    first_bond = bond_events[0] if bond_events else None
    biggest_add = max(bond_events, key=lambda e: e.additional_wei, default=None)

    lifecycle = _load_lifecycle_totals(rpc, bonding_manager=bonding_manager, delegator=wallet, from_block=from_block, to_block=snapshot_block)
    in_logs, out_logs = _load_lpt_transfers(rpc, token=token, wallet=wallet, from_block=from_block, to_block=snapshot_block)
    transfers = _summarize_transfers(wallet=wallet, in_logs=in_logs, out_logs=out_logs)
    deposits = _identify_bond_deposit_destinations(rpc, token=token, wallet=wallet, bond_events=bond_events)

    payload: Dict[str, Any] = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "wallet": wallet,
            "rpc_url": args.rpc_url,
            "lpt_token": token,
            "bonding_manager": bonding_manager,
            "from_block": from_block,
            "latest_block_at_start": latest_block,
            "snapshot_block": snapshot_block,
            "block_lag": int(args.block_lag),
        },
        "wallet_meta": {"is_contract": is_contract, "code_len_hex": max(0, len(code) - 2)},
        "snapshot": {
            "snapshot_block_timestamp": snapshot_ts,
            "bonded_now_lpt": str(_wei_to_lpt(bonded_now_wei)),
            "delegate_now": delegate_now,
        },
        "bond_events_summary": {
            "bond_events": len(bond_events),
            "bond_events_with_additional": sum(1 for e in bond_events if e.additional_wei > 0),
            "total_additional_bonded_lpt": str(_wei_to_lpt(total_additional)),
            "max_bonded_lpt": str(_wei_to_lpt(max_bonded)),
            "first_bond": {
                "block_number": first_bond.block_number,
                "timestamp": _eth_get_block_ts(rpc, block_number=first_bond.block_number, cache=ts_cache),
                "tx_hash": first_bond.tx_hash,
                "new_delegate": first_bond.new_delegate,
                "old_delegate": first_bond.old_delegate,
                "additional_lpt": str(_wei_to_lpt(first_bond.additional_wei)),
                "bonded_lpt": str(_wei_to_lpt(first_bond.bonded_wei)),
            }
            if first_bond
            else None,
            "biggest_additional": {
                "block_number": biggest_add.block_number,
                "timestamp": _eth_get_block_ts(rpc, block_number=biggest_add.block_number, cache=ts_cache),
                "tx_hash": biggest_add.tx_hash,
                "new_delegate": biggest_add.new_delegate,
                "old_delegate": biggest_add.old_delegate,
                "additional_lpt": str(_wei_to_lpt(biggest_add.additional_wei)),
                "bonded_lpt": str(_wei_to_lpt(biggest_add.bonded_wei)),
            }
            if biggest_add
            else None,
        },
        "lifecycle_totals": lifecycle,
        "lpt_transfers": transfers,
        "bond_deposit_destinations": deposits,
    }
    _write_json_atomic(out_json, payload)

    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(f"# Livepeer (Ethereum L1) — Wallet origin trace — `{wallet}`\n\n")
        f.write("## Snapshot\n\n")
        f.write(f"- Snapshot block: `{snapshot_block}` — `{_iso(snapshot_ts)}` (lag `{int(args.block_lag)}`)\n")
        f.write(f"- Wallet type: `{'contract' if is_contract else 'EOA'}`\n")
        f.write(f"- Bonded now: `{_format_decimal(_wei_to_lpt(bonded_now_wei), places=3)} LPT`\n")
        f.write(f"- Current delegate: `{delegate_now}`\n\n")

        f.write("## Bonding history (Bond events)\n\n")
        f.write(f"- Bond events: `{len(bond_events):,}` (with additional: `{sum(1 for e in bond_events if e.additional_wei > 0):,}`)\n")
        f.write(f"- Total additional bonded: `{_format_decimal(_wei_to_lpt(total_additional), places=3)} LPT`\n")
        f.write(f"- Max bonded (from events): `{_format_decimal(_wei_to_lpt(max_bonded), places=3)} LPT`\n")
        if first_bond:
            first_ts = _eth_get_block_ts(rpc, block_number=first_bond.block_number, cache=ts_cache)
            f.write(
                f"- First observed Bond: `{_iso(first_ts)}` (block `{first_bond.block_number}`) — additional `{_format_decimal(_wei_to_lpt(first_bond.additional_wei), places=3)} LPT`, bonded `{_format_decimal(_wei_to_lpt(first_bond.bonded_wei), places=3)} LPT`, delegate `{first_bond.new_delegate}`\n"
            )
        if biggest_add:
            big_ts = _eth_get_block_ts(rpc, block_number=biggest_add.block_number, cache=ts_cache)
            f.write(
                f"- Biggest single add: `{_iso(big_ts)}` (block `{biggest_add.block_number}`) — additional `{_format_decimal(_wei_to_lpt(biggest_add.additional_wei), places=3)} LPT`, delegate `{biggest_add.new_delegate}` (tx `{biggest_add.tx_hash}`)\n"
            )
        f.write("\n")

        f.write("## Bond deposit destinations (escrows)\n\n")
        if deposits["deposit_destinations"]:
            f.write("| Destination | Total bond deposits (LPT) |\n")
            f.write("|---|---:|\n")
            for row in deposits["deposit_destinations"][:10]:
                f.write(f"| `{row['to']}` | {_format_decimal(Decimal(row['bond_deposit_total_lpt']), places=3)} |\n")
        else:
            f.write("No bond deposit destinations detected.\n")
        f.write("\n")

        f.write("## Lifecycle totals (BondingManager)\n\n")
        f.write(f"- Unbond events: `{lifecycle['unbond_events']}` (total: `{_format_decimal(Decimal(lifecycle['unbond_total_lpt']), places=3)} LPT`)\n")
        f.write(f"- WithdrawStake events: `{lifecycle['withdraw_events']}` (total: `{_format_decimal(Decimal(lifecycle['withdraw_total_lpt']), places=3)} LPT`)\n")
        f.write(
            f"- EarningsClaimed events: `{lifecycle['claim_events']}` (rewards: `{_format_decimal(Decimal(lifecycle['rewards_claimed_total_lpt']), places=3)} LPT`, fees: `{_format_decimal(Decimal(lifecycle['fees_claimed_total_eth']), places=6)} ETH`)\n"
        )

        f.write("\n## LPT token transfer summary\n\n")
        f.write(f"- Inbound transfers: `{transfers['inbound_transfers']:,}` (unique senders: `{transfers['unique_senders']:,}`)\n")
        f.write(f"- Outbound transfers: `{transfers['outbound_transfers']:,}` (unique recipients: `{transfers['unique_recipients']:,}`)\n")
        f.write(f"- Total inbound: `{_format_decimal(Decimal(transfers['in_total_lpt']), places=3)} LPT`\n")
        f.write(f"- Total outbound: `{_format_decimal(Decimal(transfers['out_total_lpt']), places=3)} LPT`\n")
        f.write(f"- Net (in - out): `{_format_decimal(Decimal(transfers['net_lpt']), places=3)} LPT`\n\n")

        f.write("Top inbound senders (by total LPT):\n\n")
        f.write("| From | Total inbound (LPT) |\n")
        f.write("|---|---:|\n")
        for row in transfers["top_inbound_senders"][:10]:
            f.write(f"| `{row['from']}` | {_format_decimal(Decimal(row['lpt']), places=3)} |\n")

        f.write("\nTop outbound recipients (by total LPT):\n\n")
        f.write("| To | Total outbound (LPT) |\n")
        f.write("|---|---:|\n")
        for row in transfers["top_outbound_recipients"][:10]:
            f.write(f"| `{row['to']}` | {_format_decimal(Decimal(row['lpt']), places=3)} |\n")

        f.write("\n## Notes\n\n")
        f.write("- Bond deposits are inferred by matching the Bond event's `additional` amount to an ERC20 `Transfer` in the same transaction receipt.\n")
        f.write("- Transfers involving escrow destinations are typically protocol-internal (bond deposits + stake withdrawals), not external purchases.\n")
        f.write("- See the JSON output for raw tx hashes and evidence rows.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
