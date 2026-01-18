#!/usr/bin/env python3
"""
Generate a reproducible delegation report for the Lisar SPE program (Arbitrum One).

Data sources:
- Lisar public dashboard API (summary + transactions)
- Livepeer BondingManager (Arbitrum) via JSON-RPC eth_getLogs + eth_call

This script is intentionally stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ARBITRUM_PUBLIC_RPC = "https://arb1.arbitrum.io/rpc"

# Livepeer contracts on Arbitrum One (from livepeer/protocol deployments)
BONDING_MANAGER_PROXY = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"
LPT_TOKEN_ARBITRUM = "0x289ba1701C2F088cf0faf8B3705246331cB8A839"

# Lisar public API (observed via lisarstake.com bundle)
LISAR_API_BASE = "https://lisar-api-3-pi90.onrender.com/api/v1"
LISAR_DASHBOARD_SUMMARY_URL = f"{LISAR_API_BASE}/admin/dashboard/summary"
LISAR_DASHBOARD_TX_URL = f"{LISAR_API_BASE}/admin/dashboard/transactions"

# Topic0 hashes (cast sig-event ...)
TOPIC0_BOND = "0xe5917769f276ddca9f2ee7c6b0b33e1d1e1b61008010ce622c632dd20d168a23"
TOPIC0_UNBOND = "0x2d5d98d189bee5496a08db2a5948cb7e5e786f09d17d0c3f228eb41776c24a06"
TOPIC0_WITHDRAW_STAKE = "0x1340f1a8f3d456a649e1a12071dfa15655e3d09252131d0f980c3b405cc8dd2e"
TOPIC0_EARNINGS_CLAIMED = "0xd7eab0765b772ea6ea859d5633baf737502198012e930f257f90013d9b211094"

ERC20_TRANSFER_SELECTOR = "0xa9059cbb"


def _hex0x(data: bytes) -> str:
    return "0x" + data.hex()


def _pad_topic_address(addr: str) -> str:
    a = addr.lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return "0x" + "0" * 24 + a[2:]


def _topic_to_address(topic: str) -> str:
    if not topic.startswith("0x") or len(topic) != 66:
        raise ValueError(f"unexpected topic: {topic}")
    return "0x" + topic[-40:]


def _decode_words(data_hex: str, n_words: int) -> List[int]:
    if not data_hex.startswith("0x"):
        raise ValueError("data must be 0x-prefixed")
    s = data_hex[2:]
    need = 64 * n_words
    if len(s) < need:
        raise ValueError(f"data too short: need {need} hex chars, got {len(s)}")
    return [int(s[i : i + 64], 16) for i in range(0, need, 64)]


def _parse_amount_from_description(desc: str) -> Optional[float]:
    # Examples from Lisar dashboard:
    # - "deposited 15.7363"
    # - "bonded 0.02"
    # - "unbonded 0.02539014761696703"
    # - "withdrawn 0"
    if not isinstance(desc, str):
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)", desc)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _decode_erc20_transfer_input(input_hex: str) -> Tuple[str, int]:
    if not isinstance(input_hex, str) or not input_hex.startswith("0x"):
        raise ValueError("unexpected tx input")
    if not input_hex.startswith(ERC20_TRANSFER_SELECTOR):
        raise ValueError("not an erc20 transfer")
    s = input_hex[2:]
    if len(s) < 8 + 64 + 64:
        raise ValueError("erc20 transfer input too short")
    if s[:8].lower() != ERC20_TRANSFER_SELECTOR[2:]:
        raise ValueError("selector mismatch")
    to_addr = "0x" + s[8 : 8 + 64][-40:]
    amount = int(s[8 + 64 : 8 + 128], 16)
    return to_addr.lower(), amount


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
            headers={
                "content-type": "application/json",
                "user-agent": "embody-livepeer-research/lisar_program_delegation_report",
            },
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
    req = Request(url, headers={"user-agent": "embody-livepeer-research/lisar_program_delegation_report"})
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _utc_day(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _get_block_timestamp(client: RpcClient, cache: Dict[int, int], block_number: int) -> int:
    if block_number in cache:
        return cache[block_number]
    block = _rpc_with_retries(client, "eth_getBlockByNumber", [hex(block_number), False])
    if not block:
        raise RpcError(f"missing block {block_number}")
    ts = int(block["timestamp"], 16)
    cache[block_number] = ts
    return ts


def _get_logs_range(
    client: RpcClient,
    *,
    address: str,
    topics: list,
    from_block: int,
    to_block: int,
    max_splits: int = 24,
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


def _eth_call_get_delegator(client: RpcClient, delegator: str, at_block: Optional[int] = None) -> dict:
    # getDelegator(address)(uint256,uint256,address,uint256,uint256,uint256,uint256)
    # selector: first 4 bytes of keccak("getDelegator(address)")
    # Precomputed here to keep stdlib-only: cast sig "getDelegator(address)" => 0xa64ad595
    selector = bytes.fromhex("a64ad595")
    arg = bytes.fromhex("0" * 24 + delegator.lower()[2:])
    data = _hex0x(selector + arg)
    call_obj = {"to": BONDING_MANAGER_PROXY, "data": data}
    block_tag = hex(at_block) if at_block is not None else "latest"
    out = _rpc_with_retries(client, "eth_call", [call_obj, block_tag])
    if not isinstance(out, str) or not out.startswith("0x"):
        raise RpcError(f"unexpected eth_call output: {out!r}")
    words = _decode_words(out, 7)
    bonded_amount = words[0]
    fees = words[1]
    delegate_addr = "0x" + format(words[2], "064x")[-40:]
    delegated_amount = words[3]
    start_round = words[4]
    last_claim_round = words[5]
    next_unbonding_lock_id = words[6]
    return {
        "bondedAmount": bonded_amount,
        "fees": fees,
        "delegateAddress": delegate_addr,
        "delegatedAmount": delegated_amount,
        "startRound": start_round,
        "lastClaimRound": last_claim_round,
        "nextUnbondingLockId": next_unbonding_lock_id,
    }


@dataclass
class DelegatorRollup:
    address: str
    first_bond_ts: Optional[int] = None
    first_bond_block: Optional[int] = None
    last_bond_ts: Optional[int] = None
    last_bond_block: Optional[int] = None
    bond_events: int = 0
    bond_additional_total: int = 0
    last_bonded_amount: int = 0
    delegates: Dict[str, int] = None  # delegate -> count

    unbond_events: int = 0
    unbond_total: int = 0
    first_unbond_ts: Optional[int] = None
    last_unbond_ts: Optional[int] = None

    withdraw_events: int = 0
    withdraw_total: int = 0
    first_withdraw_ts: Optional[int] = None
    last_withdraw_ts: Optional[int] = None

    claim_events: int = 0
    rewards_claimed_total: int = 0
    fees_claimed_total: int = 0

    current_bonded_amount: Optional[int] = None
    current_delegate: Optional[str] = None

    def __post_init__(self):
        if self.delegates is None:
            self.delegates = {}


def _apply_min(current: Optional[int], candidate: int) -> int:
    return candidate if current is None else min(current, candidate)


def _apply_max(current: Optional[int], candidate: int) -> int:
    return candidate if current is None else max(current, candidate)


def _to_lpt(amount_wei: int) -> float:
    return amount_wei / 1e18


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", default=os.environ.get("ARBITRUM_RPC_URL", ARBITRUM_PUBLIC_RPC))
    parser.add_argument("--out-dir", default="artifacts/livepeer-lisar-spe-delegation")
    parser.add_argument("--tx-limit", type=int, default=5000)
    parser.add_argument("--from-block", type=int, default=0, help="0 = auto (based on earliest Lisar tx)")
    parser.add_argument("--to-block", type=int, default=0, help="0 = latest")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    summary = _http_get_json(LISAR_DASHBOARD_SUMMARY_URL)
    txs = _http_get_json(f"{LISAR_DASHBOARD_TX_URL}?limit={args.tx_limit}")

    with open(os.path.join(args.out_dir, "lisar_dashboard_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")

    with open(os.path.join(args.out_dir, "lisar_dashboard_transactions.json"), "w", encoding="utf-8") as f:
        json.dump(txs, f, indent=2, sort_keys=True)
        f.write("\n")

    tx_rows = (txs or {}).get("data") or []
    tx_event_counts = Counter()
    tx_amount_sums = defaultdict(float)
    tx_addresses_by_event: Dict[str, set] = defaultdict(set)
    for row in tx_rows:
        ev = row.get("event")
        if not isinstance(ev, str):
            continue
        tx_event_counts[ev] += 1
        addr = row.get("address")
        if isinstance(addr, str):
            tx_addresses_by_event[ev].add(addr.lower())
        amt = _parse_amount_from_description(row.get("description") or "")
        if amt is not None:
            tx_amount_sums[ev] += amt

    bond_unbond_rows = [t for t in tx_rows if t.get("event") in ("bond", "unbond")]
    lisar_delegators = sorted({t["address"].lower() for t in bond_unbond_rows if isinstance(t.get("address"), str)})

    rpc = RpcClient(args.rpc_url)
    latest_hex = _rpc_with_retries(rpc, "eth_blockNumber", [])
    latest_block = int(latest_hex, 16)
    to_block = latest_block if args.to_block == 0 else args.to_block

    # Determine a tight-ish scan window by looking up the on-chain block for Lisar bond/unbond txs.
    min_seen_block: Optional[int] = None
    max_seen_block: Optional[int] = None
    receipt_cache: Dict[str, dict] = {}
    for row in bond_unbond_rows:
        tx_hash = row.get("transaction_hash")
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            continue
        if tx_hash in receipt_cache:
            receipt = receipt_cache[tx_hash]
        else:
            receipt = _rpc_with_retries(rpc, "eth_getTransactionReceipt", [tx_hash])
            receipt_cache[tx_hash] = receipt
        if not receipt or "blockNumber" not in receipt:
            continue
        bn = int(receipt["blockNumber"], 16)
        min_seen_block = _apply_min(min_seen_block, bn)
        max_seen_block = _apply_max(max_seen_block, bn)

    auto_from = min_seen_block - 50_000 if min_seen_block is not None else 5856381
    from_block = auto_from if args.from_block == 0 else args.from_block
    if from_block < 0:
        from_block = 0
    if max_seen_block is not None:
        to_block = max(to_block, max_seen_block)

    delegator_topics = [_pad_topic_address(a) for a in lisar_delegators]
    if not delegator_topics:
        raise SystemExit("No Lisar bond/unbond delegators found from Lisar dashboard API")

    block_ts_cache: Dict[int, int] = {}

    # Pull logs for *these* delegators only (topics OR-list) within the window.
    bond_logs = _get_logs_range(
        rpc,
        address=BONDING_MANAGER_PROXY,
        topics=[TOPIC0_BOND, None, None, delegator_topics],
        from_block=from_block,
        to_block=to_block,
    )
    unbond_logs = _get_logs_range(
        rpc,
        address=BONDING_MANAGER_PROXY,
        topics=[TOPIC0_UNBOND, None, delegator_topics],
        from_block=from_block,
        to_block=to_block,
    )
    withdraw_logs = _get_logs_range(
        rpc,
        address=BONDING_MANAGER_PROXY,
        topics=[TOPIC0_WITHDRAW_STAKE, delegator_topics],
        from_block=from_block,
        to_block=to_block,
    )
    claim_logs = _get_logs_range(
        rpc,
        address=BONDING_MANAGER_PROXY,
        topics=[TOPIC0_EARNINGS_CLAIMED, None, delegator_topics],
        from_block=from_block,
        to_block=to_block,
    )

    # Decode + roll up
    rollups: Dict[str, DelegatorRollup] = {a: DelegatorRollup(address=a) for a in lisar_delegators}

    def ts_for_block(bn: int) -> int:
        return _get_block_timestamp(rpc, block_ts_cache, bn)

    # Bonds
    for log in bond_logs:
        topics = log.get("topics") or []
        if len(topics) < 4:
            continue
        delegator = _topic_to_address(topics[3])
        new_delegate = _topic_to_address(topics[1])
        additional, bonded = _decode_words(log.get("data") or "0x", 2)
        bn = int(log["blockNumber"], 16)
        ts = ts_for_block(bn)

        r = rollups.get(delegator) or DelegatorRollup(address=delegator)
        r.bond_events += 1
        r.bond_additional_total += additional
        r.last_bonded_amount = bonded
        r.delegates[new_delegate] = r.delegates.get(new_delegate, 0) + 1
        r.first_bond_ts = _apply_min(r.first_bond_ts, ts)
        r.first_bond_block = _apply_min(r.first_bond_block, bn) if r.first_bond_block is not None else bn
        r.last_bond_ts = _apply_max(r.last_bond_ts, ts)
        r.last_bond_block = _apply_max(r.last_bond_block, bn) if r.last_bond_block is not None else bn
        rollups[delegator] = r

    # Unbonds
    for log in unbond_logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        delegator = _topic_to_address(topics[2])
        _lock_id, amount, _withdraw_round = _decode_words(log.get("data") or "0x", 3)
        bn = int(log["blockNumber"], 16)
        ts = ts_for_block(bn)
        r = rollups.get(delegator) or DelegatorRollup(address=delegator)
        r.unbond_events += 1
        r.unbond_total += amount
        r.first_unbond_ts = _apply_min(r.first_unbond_ts, ts)
        r.last_unbond_ts = _apply_max(r.last_unbond_ts, ts)
        rollups[delegator] = r

    # Withdraw stake
    for log in withdraw_logs:
        topics = log.get("topics") or []
        if len(topics) < 2:
            continue
        delegator = _topic_to_address(topics[1])
        _lock_id, amount, _withdraw_round = _decode_words(log.get("data") or "0x", 3)
        bn = int(log["blockNumber"], 16)
        ts = ts_for_block(bn)
        r = rollups.get(delegator) or DelegatorRollup(address=delegator)
        r.withdraw_events += 1
        r.withdraw_total += amount
        r.first_withdraw_ts = _apply_min(r.first_withdraw_ts, ts)
        r.last_withdraw_ts = _apply_max(r.last_withdraw_ts, ts)
        rollups[delegator] = r

    # Earnings claims
    for log in claim_logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        delegator = _topic_to_address(topics[2])
        rewards, fees, _start_round, _end_round = _decode_words(log.get("data") or "0x", 4)
        r = rollups.get(delegator) or DelegatorRollup(address=delegator)
        r.claim_events += 1
        r.rewards_claimed_total += rewards
        r.fees_claimed_total += fees
        rollups[delegator] = r

    # Current bonded state for each delegator
    for delegator in rollups.keys():
        state = _eth_call_get_delegator(rpc, delegator)
        rollups[delegator].current_bonded_amount = int(state["bondedAmount"])
        rollups[delegator].current_delegate = state["delegateAddress"]

    # Daily aggregates (only for Lisar delegators)
    daily: Dict[str, Dict[str, Any]] = {}

    def bump(day: str, key: str, inc: int = 1):
        d = daily.setdefault(day, {})
        d[key] = int(d.get(key, 0)) + inc

    def bump_amount(day: str, key: str, amount: int):
        d = daily.setdefault(day, {})
        d[key] = str(int(d.get(key, "0")) + amount)

    for log in bond_logs:
        bn = int(log["blockNumber"], 16)
        ts = ts_for_block(bn)
        day = _utc_day(ts)
        additional, _bonded = _decode_words(log.get("data") or "0x", 2)
        bump(day, "bond_events", 1)
        bump_amount(day, "bond_additional", additional)

    for log in unbond_logs:
        bn = int(log["blockNumber"], 16)
        ts = ts_for_block(bn)
        day = _utc_day(ts)
        _lock_id, amount, _withdraw_round = _decode_words(log.get("data") or "0x", 3)
        bump(day, "unbond_events", 1)
        bump_amount(day, "unbond_amount", amount)

    for log in withdraw_logs:
        bn = int(log["blockNumber"], 16)
        ts = ts_for_block(bn)
        day = _utc_day(ts)
        _lock_id, amount, _withdraw_round = _decode_words(log.get("data") or "0x", 3)
        bump(day, "withdraw_events", 1)
        bump_amount(day, "withdraw_amount", amount)

    # Top-level summary
    total_current_bonded = sum((r.current_bonded_amount or 0) for r in rollups.values())
    active_delegators = [r for r in rollups.values() if (r.current_bonded_amount or 0) > 0]
    ever_bonded = [r for r in rollups.values() if r.bond_events > 0]

    program_start_ts = min((r.first_bond_ts for r in ever_bonded if r.first_bond_ts is not None), default=None)
    program_end_ts = max((r.last_bond_ts for r in ever_bonded if r.last_bond_ts is not None), default=None)

    dashboard_summary = (summary or {}).get("data") or summary
    dashboard_total_lpt_delegated = None
    if isinstance(dashboard_summary, dict) and dashboard_summary.get("totalLptDelegated") is not None:
        try:
            dashboard_total_lpt_delegated = float(dashboard_summary["totalLptDelegated"])
        except (TypeError, ValueError):
            dashboard_total_lpt_delegated = None

    # Decode Lisar dashboard "deposit"/"withdraw" tx hashes (best-effort) to understand funnel flows.
    tx_cache: Dict[str, dict] = {}
    deposit_rows = [t for t in tx_rows if t.get("event") == "deposit"]
    withdraw_rows = [t for t in tx_rows if t.get("event") == "withdraw"]
    deposit_transfer_senders = set()
    deposit_transfer_recipients = set()
    deposit_transfer_total = 0
    deposit_transfer_recipient_mismatches = []
    withdraw_transfer_destinations = set()
    withdraw_transfer_total = 0
    withdraw_tx_types = Counter()

    def get_tx(tx_hash: str) -> Optional[dict]:
        if tx_hash in tx_cache:
            return tx_cache[tx_hash]
        tx = _rpc_with_retries(rpc, "eth_getTransactionByHash", [tx_hash])
        if isinstance(tx, dict):
            tx_cache[tx_hash] = tx
            return tx
        return None

    for row in deposit_rows:
        tx_hash = row.get("transaction_hash")
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            continue
        tx = get_tx(tx_hash)
        if tx is None:
            continue
        if (tx.get("to") or "").lower() != LPT_TOKEN_ARBITRUM.lower():
            continue
        try:
            recipient, amount = _decode_erc20_transfer_input(tx.get("input") or "")
        except ValueError:
            continue
        sender = (tx.get("from") or "").lower()
        if sender:
            deposit_transfer_senders.add(sender)
        deposit_transfer_recipients.add(recipient)
        deposit_transfer_total += amount
        expected_recipient = (row.get("address") or "").lower()
        if expected_recipient and expected_recipient != recipient:
            deposit_transfer_recipient_mismatches.append(
                {"tx": tx_hash, "row_address": expected_recipient, "transfer_to": recipient}
            )

    for row in withdraw_rows:
        tx_hash = row.get("transaction_hash")
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            continue
        tx = get_tx(tx_hash)
        if tx is None:
            continue
        to_contract = (tx.get("to") or "").lower()
        if to_contract == LPT_TOKEN_ARBITRUM.lower():
            try:
                recipient, amount = _decode_erc20_transfer_input(tx.get("input") or "")
            except ValueError:
                withdraw_tx_types["erc20_transfer_parse_error"] += 1
                continue
            withdraw_tx_types["erc20_transfer"] += 1
            withdraw_transfer_destinations.add(recipient)
            withdraw_transfer_total += amount
        elif to_contract == BONDING_MANAGER_PROXY.lower():
            withdraw_tx_types["bonding_manager_call"] += 1
        else:
            withdraw_tx_types["other"] += 1

    deposit_only_addresses = sorted(
        a for a in tx_addresses_by_event.get("deposit", set()) if a not in tx_addresses_by_event.get("bond", set())
    )

    computed = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "inputs": {
            "rpc_url": args.rpc_url,
            "bonding_manager_proxy": BONDING_MANAGER_PROXY,
            "lpt_token": LPT_TOKEN_ARBITRUM,
            "lisar_dashboard_summary_url": LISAR_DASHBOARD_SUMMARY_URL,
            "lisar_dashboard_transactions_url": f"{LISAR_DASHBOARD_TX_URL}?limit={args.tx_limit}",
            "from_block": from_block,
            "to_block": to_block,
            "lisar_delegators_count_from_dashboard_tx": len(lisar_delegators),
        },
        "lisar_dashboard_summary": dashboard_summary,
        "lisar_dashboard_transactions": {
            "rows": len(tx_rows),
            "event_counts": dict(tx_event_counts),
            "unique_addresses_by_event": {k: len(v) for k, v in tx_addresses_by_event.items()},
            "amount_sums_lpt_from_description": dict(tx_amount_sums),
            "deposit_only_addresses": deposit_only_addresses,
            "deposit_transfers": {
                "unique_senders": len(deposit_transfer_senders),
                "unique_recipients": len(deposit_transfer_recipients),
                "transfer_total_lpt_from_input": _to_lpt(deposit_transfer_total),
                "recipient_mismatches": deposit_transfer_recipient_mismatches,
            },
            "withdraw_transfers": {
                "tx_types": dict(withdraw_tx_types),
                "unique_destinations": len(withdraw_transfer_destinations),
                "transfer_total_lpt_from_input": _to_lpt(withdraw_transfer_total),
            },
        },
        "computed": {
            "program_start_utc": _iso(program_start_ts) if program_start_ts is not None else None,
            "program_end_utc": _iso(program_end_ts) if program_end_ts is not None else None,
            "delegators_ever_bonded": len(ever_bonded),
            "delegators_active_now": len(active_delegators),
            "current_total_bonded_lpt": _to_lpt(total_current_bonded),
            "bond_additional_total_lpt": _to_lpt(sum(r.bond_additional_total for r in rollups.values())),
            "unbond_total_lpt": _to_lpt(sum(r.unbond_total for r in rollups.values())),
            "withdraw_total_lpt": _to_lpt(sum(r.withdraw_total for r in rollups.values())),
            "claim_events_total": sum(r.claim_events for r in rollups.values()),
            "dashboard_total_lpt_delegated": dashboard_total_lpt_delegated,
            "dashboard_total_lpt_delegated_delta_vs_current_bonded": (
                _to_lpt(total_current_bonded) - dashboard_total_lpt_delegated
                if dashboard_total_lpt_delegated is not None
                else None
            ),
            "dashboard_total_lpt_delegated_delta_vs_bond_additional": (
                _to_lpt(sum(r.bond_additional_total for r in rollups.values())) - dashboard_total_lpt_delegated
                if dashboard_total_lpt_delegated is not None
                else None
            ),
        },
        "daily": {k: daily[k] for k in sorted(daily.keys())},
        "delegators": {
            addr: {
                **asdict(r),
                "bond_additional_total_lpt": _to_lpt(r.bond_additional_total),
                "unbond_total_lpt": _to_lpt(r.unbond_total),
                "withdraw_total_lpt": _to_lpt(r.withdraw_total),
                "current_bonded_lpt": _to_lpt(r.current_bonded_amount or 0),
            }
            for addr, r in sorted(rollups.items())
        },
    }

    report_json_path = os.path.join(args.out_dir, "report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(computed, f, indent=2, sort_keys=True)
        f.write("\n")

    # A short human summary
    report_md_path = os.path.join(args.out_dir, "report.md")
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# Lisar SPE — Delegation On-Chain Report (Arbitrum One)\n\n")
        f.write(f"- Generated: `{computed['generated_at_utc']}`\n")
        f.write(f"- Scan window: blocks `{from_block}` → `{to_block}`\n")
        if computed["computed"]["program_start_utc"]:
            f.write(f"- First observed Lisar bond: `{computed['computed']['program_start_utc']}`\n")
        if computed["computed"]["dashboard_total_lpt_delegated"] is not None:
            f.write(f"- Lisar dashboard `totalLptDelegated`: `{computed['computed']['dashboard_total_lpt_delegated']:.6f} LPT`\n")
            if computed["computed"]["dashboard_total_lpt_delegated_delta_vs_current_bonded"] is not None:
                f.write(
                    f"- Dashboard vs on-chain current bonded delta: `{computed['computed']['dashboard_total_lpt_delegated_delta_vs_current_bonded']:.6f} LPT`\n"
                )
        f.write("\n## Summary\n\n")
        f.write(f"- Delegators (ever bonded): **{computed['computed']['delegators_ever_bonded']}**\n")
        f.write(f"- Delegators (active now): **{computed['computed']['delegators_active_now']}**\n")
        f.write(f"- Current total bonded: **{computed['computed']['current_total_bonded_lpt']:.6f} LPT**\n")
        f.write(f"- Total bonded via Bond events (additional): **{computed['computed']['bond_additional_total_lpt']:.6f} LPT**\n")
        f.write(f"- Total unbonded: **{computed['computed']['unbond_total_lpt']:.6f} LPT**\n")
        f.write(f"- Total withdrawn: **{computed['computed']['withdraw_total_lpt']:.6f} LPT**\n")
        f.write(f"- EarningsClaimed events (total): **{computed['computed']['claim_events_total']}**\n")
        f.write("\n## Notes\n\n")
        f.write("- This report scopes to delegators visible in Lisar’s public dashboard transactions.\n")
        f.write("- Values are on-chain LPT (18 decimals) from the Livepeer BondingManager.\n")
        f.write("- “Bond additional” is the `additionalAmount` field from `Bond` events.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
