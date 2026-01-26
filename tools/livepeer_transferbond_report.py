#!/usr/bin/env python3
"""
Livepeer (Arbitrum) — TransferBond activity report (stake rotation / wallet splitting primitive).

Why this exists
---------------
Livepeer's BondingManager exposes `transferBond(...)` which emits `TransferBond`.
This can move bonded stake between addresses without a fresh "Bond" event, which means:
- "new delegator" counts can be overstated if we only look at Bond events,
- whales can rotate/split stake across addresses without touching an exchange.

This report:
- scans `TransferBond` events for a recent window,
- aggregates amount + participants,
- (best-effort) validates whether each TransferBond tx also emits Unbond+Rebond logs.

Stdlib-only.

Outputs
-------
- research/livepeer-transferbond-rotation.json
- research/livepeer-transferbond-rotation.md
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
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

ARBITRUM_PUBLIC_RPC = "https://arb1.arbitrum.io/rpc"
LIVEPEER_BONDING_MANAGER_ARB = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"

TOPIC0 = {
    # cast sig-event "TransferBond(address,address,uint256,uint256,uint256)"
    "TransferBond": "0xf136b986590e86cf1abd7b6600186a7a1178ad3cbbdf0f3312e79f6214a2a567",
    # cast sig-event "Unbond(address,address,uint256,uint256,uint256)"
    "Unbond": "0x2d5d98d189bee5496a08db2a5948cb7e5e786f09d17d0c3f228eb41776c24a06",
    # cast sig-event "Rebond(address,address,uint256,uint256)"
    "Rebond": "0x9f5b64cc71e1e26ff178caaa7877a04d8ce66fde989251870e80e6fbee690c17",
}

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
    def __init__(self, rpc_url: str, *, timeout_s: int = 45, user_agent: str = "livepeer-transferbond-report") -> None:
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
            raise RpcError(f"bad JSON: {e}") from e

        if not isinstance(data, dict):
            raise RpcError("bad JSON-RPC response (not dict)")
        if data.get("error") is not None:
            err = data.get("error") or {}
            msg = str(err.get("message") or "unknown error")
            raise RpcError(msg)
        return data.get("result")


def _rpc_with_retries(client: RpcClient, method: str, params: list, *, max_tries: int = 8) -> Any:
    last_err: Exception | None = None
    for attempt in range(1, max_tries + 1):
        try:
            return client.call(method, params)
        except RpcError as e:
            last_err = e
            msg = str(e).lower()
            retryable = any(
                s in msg
                for s in (
                    "timeout",
                    "timed out",
                    "429",
                    "rate limit",
                    "too many requests",
                    "gateway timeout",
                    "bad gateway",
                    "connection reset",
                    "temporary",
                    "overloaded",
                )
            )
            if not retryable or attempt == max_tries:
                raise
            sleep_s = min(2 ** (attempt - 1), 30.0)
            retry_after_s = getattr(e, "retry_after_s", None)
            if isinstance(retry_after_s, int) and retry_after_s > 0:
                sleep_s = max(sleep_s, float(retry_after_s))
            sleep_s = sleep_s * (1 + random.uniform(-0.15, 0.15))
            time.sleep(max(0.5, sleep_s))
    if last_err is not None:
        raise last_err
    raise RuntimeError("unreachable")


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _topic_to_address(topic_hex: str) -> str:
    t = str(topic_hex).lower()
    if t.startswith("0x"):
        t = t[2:]
    if len(t) != 64:
        raise ValueError(f"bad topic: {topic_hex}")
    return "0x" + t[-40:]


def _decode_words(data_hex: str, n: int) -> List[int]:
    if not str(data_hex).startswith("0x"):
        raise ValueError("data must be 0x-prefixed")
    hex_str = str(data_hex)[2:]
    need = 64 * n
    if len(hex_str) < need:
        raise ValueError(f"data too short: need {need} hex chars, got {len(hex_str)}")
    return [int(hex_str[i : i + 64], 16) for i in range(0, need, 64)]


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _fmt_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _block_number(client: RpcClient) -> int:
    out = _rpc_with_retries(client, "eth_blockNumber", [])
    return int(str(out), 16)


def _get_logs(client: RpcClient, *, address: str, from_block: int, to_block: int, topics: list) -> List[Dict[str, Any]]:
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


def _get_logs_chunked(
    client: RpcClient,
    *,
    address: str,
    from_block: int,
    to_block: int,
    topics: list,
    chunk_size: int,
) -> Iterable[Dict[str, Any]]:
    b = int(from_block)
    end = int(to_block)
    while b <= end:
        chunk_to = min(end, b + int(chunk_size) - 1)
        logs = _get_logs(client, address=address, from_block=b, to_block=chunk_to, topics=topics)
        if isinstance(logs, list):
            for log in logs:
                if isinstance(log, dict):
                    yield log
        b = chunk_to + 1


def _get_receipt(client: RpcClient, tx_hash: str) -> Dict[str, Any] | None:
    txh = str(tx_hash).lower()
    out = _rpc_with_retries(client, "eth_getTransactionReceipt", [txh])
    return out if isinstance(out, dict) else None


def _parse_receipt_for_unbond_rebond(receipt: Dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    unbond_by_delegator: dict[str, int] = defaultdict(int)
    rebond_by_delegator: dict[str, int] = defaultdict(int)
    logs = receipt.get("logs") or []
    if not isinstance(logs, list):
        return dict(unbond_by_delegator), dict(rebond_by_delegator)
    for log in logs:
        if not isinstance(log, dict):
            continue
        topics = log.get("topics") or []
        if not isinstance(topics, list) or not topics:
            continue
        topic0 = str(topics[0]).lower()
        data_hex = str(log.get("data") or "0x")
        try:
            if topic0 == TOPIC0["Unbond"]:
                # Unbond(address delegate, address delegator, uint256 unbondingLockId, uint256 amount, uint256 withdrawRound)
                if len(topics) < 3:
                    continue
                delegator = _topic_to_address(topics[2]).lower()
                _lock_id, amount, _withdraw_round = _decode_words(data_hex, 3)
                unbond_by_delegator[delegator] += int(amount)
            elif topic0 == TOPIC0["Rebond"]:
                # Rebond(address delegate, address delegator, uint256 unbondingLockId, uint256 amount)
                if len(topics) < 3:
                    continue
                delegator = _topic_to_address(topics[2]).lower()
                _lock_id, amount = _decode_words(data_hex, 2)
                rebond_by_delegator[delegator] += int(amount)
        except Exception:
            continue
    return dict(unbond_by_delegator), dict(rebond_by_delegator)


@dataclass(frozen=True)
class TransferBondEvent:
    block_number: int
    tx_hash: str
    old_delegator: str
    new_delegator: str
    old_lock_id: int
    new_lock_id: int
    amount_wei: int


def _quantiles(values: List[int], ps: List[float]) -> Dict[str, int]:
    if not values:
        return {}
    xs = sorted(values)
    out: Dict[str, int] = {}
    n = len(xs)
    for p in ps:
        if p <= 0:
            idx = 0
        elif p >= 1:
            idx = n - 1
        else:
            idx = int(round((n - 1) * p))
        out[str(p)] = int(xs[idx])
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arb-rpc", default=ARBITRUM_PUBLIC_RPC)
    parser.add_argument("--bonding-manager", default=LIVEPEER_BONDING_MANAGER_ARB)
    parser.add_argument("--days", type=int, default=365, help="How many days back to scan (approx; uses blocks/day).")
    parser.add_argument("--blocks-per-day", type=int, default=7200)
    parser.add_argument("--from-block", type=int, default=0, help="0 = computed from --days")
    parser.add_argument("--to-block", type=int, default=0, help="0 = latest")
    parser.add_argument("--log-chunk-size", type=int, default=50_000, help="Block chunk size for eth_getLogs.")
    parser.add_argument("--validate-receipts", action="store_true", help="Fetch tx receipts to validate Unbond+Rebond presence (slower).")
    parser.add_argument("--out-json", default="research/livepeer-transferbond-rotation.json")
    parser.add_argument("--out-md", default="research/livepeer-transferbond-rotation.md")
    args = parser.parse_args()

    client = RpcClient(str(args.arb_rpc), user_agent="livepeer-delegation-research/transferbond")
    latest = _block_number(client)
    to_block = int(args.to_block) or int(latest)
    if int(args.from_block) > 0:
        from_block = int(args.from_block)
    else:
        from_block = max(0, int(to_block) - int(args.days) * int(args.blocks_per_day))

    if from_block > to_block:
        raise SystemExit("--from-block must be <= --to-block")

    topic0 = str(TOPIC0["TransferBond"])
    print(f"scan TransferBond logs: {from_block:,}..{to_block:,}")

    amount_out_by_old: Dict[str, int] = defaultdict(int)
    amount_in_by_new: Dict[str, int] = defaultdict(int)
    count_by_old: Counter[str] = Counter()
    count_by_new: Counter[str] = Counter()
    fanout_by_old: Dict[str, set[str]] = defaultdict(set)
    amounts: List[int] = []
    events: List[TransferBondEvent] = []

    # Receipt validation stats.
    receipts_cache: Dict[str, Dict[str, Any] | None] = {}
    validated_events = 0
    validated_amount = 0
    receipt_missing = 0

    def validate(e: TransferBondEvent) -> tuple[bool, str | None]:
        if not bool(args.validate_receipts):
            return False, None
        txh = str(e.tx_hash).lower()
        if txh not in receipts_cache:
            receipts_cache[txh] = _get_receipt(client, txh)
        receipt = receipts_cache.get(txh)
        if receipt is None:
            return False, "missing_receipt"
        unbond_by_del, rebond_by_del = _parse_receipt_for_unbond_rebond(receipt)
        unbond_amt = int(unbond_by_del.get(e.old_delegator, 0))
        rebond_amt = int(rebond_by_del.get(e.new_delegator, 0))
        ok = unbond_amt >= int(e.amount_wei) and rebond_amt >= int(e.amount_wei)
        if ok:
            return True, None
        return False, "missing_unbond_or_rebond"

    for log in _get_logs_chunked(
        client,
        address=str(args.bonding_manager),
        from_block=from_block,
        to_block=to_block,
        topics=[topic0],
        chunk_size=int(args.log_chunk_size),
    ):
        topics = log.get("topics") or []
        if not isinstance(topics, list) or len(topics) < 3:
            continue
        try:
            old_delegator = _topic_to_address(topics[1]).lower()
            new_delegator = _topic_to_address(topics[2]).lower()
        except Exception:
            continue
        try:
            old_lock_id, new_lock_id, amount = _decode_words(str(log.get("data") or "0x"), 3)
        except Exception:
            continue
        if int(amount) <= 0:
            continue
        txh = str(log.get("transactionHash") or "").lower()
        if not txh.startswith("0x") or len(txh) != 66:
            continue
        bn = int(str(log.get("blockNumber") or "0x0"), 16)
        if bn <= 0:
            continue

        e = TransferBondEvent(
            block_number=int(bn),
            tx_hash=txh,
            old_delegator=str(old_delegator),
            new_delegator=str(new_delegator),
            old_lock_id=int(old_lock_id),
            new_lock_id=int(new_lock_id),
            amount_wei=int(amount),
        )

        events.append(e)
        amounts.append(int(amount))
        amount_out_by_old[old_delegator] += int(amount)
        amount_in_by_new[new_delegator] += int(amount)
        count_by_old[old_delegator] += 1
        count_by_new[new_delegator] += 1
        fanout_by_old[old_delegator].add(new_delegator)

        ok, reason = validate(e)
        if bool(args.validate_receipts):
            if reason == "missing_receipt":
                receipt_missing += 1
            if ok:
                validated_events += 1
                validated_amount += int(amount)

    total_events = len(events)
    total_amount_wei = sum(e.amount_wei for e in events)

    top_out = sorted(amount_out_by_old.items(), key=lambda kv: kv[1], reverse=True)[:15]
    top_in = sorted(amount_in_by_new.items(), key=lambda kv: kv[1], reverse=True)[:15]
    top_fanout = sorted(((a, len(s)) for a, s in fanout_by_old.items()), key=lambda kv: kv[1], reverse=True)[:15]

    largest_events = sorted(events, key=lambda e: e.amount_wei, reverse=True)[:25]

    out_json: Dict[str, Any] = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "arb_rpc": str(args.arb_rpc),
        "bonding_manager": _normalize_address(str(args.bonding_manager)),
        "range": {"from_block": int(from_block), "to_block": int(to_block), "days_approx": int(args.days)},
        "topic0": dict(TOPIC0),
        "totals": {
            "transferbond_events": int(total_events),
            "unique_old_delegators": int(len(amount_out_by_old)),
            "unique_new_delegators": int(len(amount_in_by_new)),
            "total_transferred_lpt": str(_wei_to_lpt(total_amount_wei)),
            "total_transferred_wei": int(total_amount_wei),
            "amount_quantiles_wei": _quantiles(amounts, [0.0, 0.5, 0.9, 0.99, 1.0]),
        },
        "receipt_validation": {
            "enabled": bool(args.validate_receipts),
            "validated_events": int(validated_events) if bool(args.validate_receipts) else None,
            "validated_amount_wei": int(validated_amount) if bool(args.validate_receipts) else None,
            "validated_amount_lpt": str(_wei_to_lpt(validated_amount)) if bool(args.validate_receipts) else None,
            "missing_receipt_events": int(receipt_missing) if bool(args.validate_receipts) else None,
            "notes": [
                "Validation is best-effort: checks whether the tx receipt contains Unbond(old) and Rebond(new) amounts >= TransferBond.amount.",
                "Multiple TransferBond calls in one tx can make this check conservative.",
            ],
        },
        "top_by_amount_out": [{"old_delegator": a, "events": int(count_by_old.get(a) or 0), "amount_lpt": str(_wei_to_lpt(v)), "amount_wei": int(v)} for a, v in top_out],
        "top_by_amount_in": [{"new_delegator": a, "events": int(count_by_new.get(a) or 0), "amount_lpt": str(_wei_to_lpt(v)), "amount_wei": int(v)} for a, v in top_in],
        "top_by_fanout": [{"old_delegator": a, "unique_new_delegators": int(n), "events": int(count_by_old.get(a) or 0)} for a, n in top_fanout],
        "largest_events": [
            {
                "block_number": int(e.block_number),
                "tx_hash": str(e.tx_hash),
                "old_delegator": str(e.old_delegator),
                "new_delegator": str(e.new_delegator),
                "amount_lpt": str(_wei_to_lpt(int(e.amount_wei))),
                "amount_wei": int(e.amount_wei),
            }
            for e in largest_events
        ],
        "notes": [
            "TransferBond is a stake-rotation primitive: it can move bonded stake between addresses without a fresh Bond event.",
            "This does NOT imply selling; it is consistent with operational wallet rotation or stake splitting.",
            "Amounts are denominated in LPT (18 decimals).",
        ],
    }

    _write_json(str(args.out_json), out_json)

    total_lpt = _wei_to_lpt(total_amount_wei)
    lines: List[str] = []
    lines.append("---")
    lines.append('title: "Livepeer: TransferBond stake rotation (on-chain)"')
    lines.append('description: "Evidence pack: TransferBond activity on Livepeer Arbitrum BondingManager to quantify stake rotation / wallet splitting behavior."')
    lines.append("---")
    lines.append("")
    lines.append("# Livepeer: TransferBond stake rotation (on-chain)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- Arbitrum RPC: `{str(args.arb_rpc)}`")
    lines.append(f"- BondingManager: `{_normalize_address(str(args.bonding_manager))}`")
    lines.append(f"- Range scanned: `{from_block:,}..{to_block:,}` (~{int(args.days)}d)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- TransferBond events: **{total_events:,}**")
    lines.append(f"- Unique senders (oldDelegator): **{len(amount_out_by_old):,}**")
    lines.append(f"- Unique recipients (newDelegator): **{len(amount_in_by_new):,}**")
    lines.append(f"- Total transferred: **{_fmt_lpt(total_lpt)} LPT**")
    if amounts:
        q = _quantiles(amounts, [0.5, 0.9, 0.99])
        lines.append(
            "- Amount quantiles (LPT): "
            + ", ".join(
                [
                    f"p50={_fmt_lpt(_wei_to_lpt(int(q.get('0.5') or 0)), places=3)}",
                    f"p90={_fmt_lpt(_wei_to_lpt(int(q.get('0.9') or 0)), places=3)}",
                    f"p99={_fmt_lpt(_wei_to_lpt(int(q.get('0.99') or 0)), places=3)}",
                ]
            )
        )
    lines.append("")
    lines.append("## Top senders (by transferred amount)")
    lines.append("")
    for row in out_json["top_by_amount_out"]:
        lines.append(
            f"- `{row['old_delegator']}`: **{_fmt_lpt(_wei_to_lpt(int(row['amount_wei'])), places=3)} LPT** across {int(row['events'])} events"
        )
    lines.append("")
    lines.append("## Top recipients (by received amount)")
    lines.append("")
    for row in out_json["top_by_amount_in"]:
        lines.append(
            f"- `{row['new_delegator']}`: **{_fmt_lpt(_wei_to_lpt(int(row['amount_wei'])), places=3)} LPT** across {int(row['events'])} events"
        )
    lines.append("")
    lines.append("## Most “split-like” senders (fanout by unique recipient count)")
    lines.append("")
    for row in out_json["top_by_fanout"]:
        lines.append(f"- `{row['old_delegator']}`: {int(row['unique_new_delegators'])} unique recipients across {int(row['events'])} events")
    if bool(args.validate_receipts):
        lines.append("")
        lines.append("## Receipt validation (best-effort)")
        lines.append("")
        lines.append(f"- Validated events (Unbond+Rebond present): **{validated_events:,}** / {total_events:,}")
        lines.append(f"- Validated amount: **{_fmt_lpt(_wei_to_lpt(validated_amount))} LPT**")
        if receipt_missing:
            lines.append(f"- Missing receipt: **{receipt_missing:,}** events")
        lines.append("- Note: multiple TransferBond calls in one tx can make validation conservative.")
    lines.append("")
    lines.append("## Largest TransferBond events (examples)")
    lines.append("")
    for e in out_json["largest_events"][:10]:
        lines.append(
            f"- { _fmt_lpt(_wei_to_lpt(int(e['amount_wei'])), places=3) } LPT: `{e['old_delegator']}` → `{e['new_delegator']}` (tx `{e['tx_hash']}`)"
        )
    lines.append("")
    lines.append("## Notes / limitations")
    lines.append("")
    lines.append("- TransferBond indicates stake rotation, not necessarily selling.")
    lines.append("- This report does not (yet) attribute *delegate* changes; it focuses on delegator address rotation.")
    lines.append("- This report does not prove common ownership, but large fanout patterns are consistent with wallet-splitting behavior.")
    lines.append("")
    lines.append(f"Raw output: see `{str(args.out_json)}`.")
    lines.append("")

    _write_text(str(args.out_md), "\n".join(lines))

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

