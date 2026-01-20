#!/usr/bin/env python3
"""
Livepeer — Ethereum L1 follow-up for Arbitrum bridge-outs (LPT).

Goal
----
When we see large Arbitrum `LPT` exits as "burn to zero", those are typically
bridge-outs. We already decode the L2 burn txs to the L1 recipients in:

  research/arbitrum-bridge-out-decode.json

This script follows the *L1 recipients* and answers:
  "After LPT arrives on L1, where does it go next?"

We use only JSON-RPC calls (no explorer keys):
- `eth_getLogs` on the L1 LPT token's `Transfer` events (outgoing transfers
  from each recipient)
- `eth_call` for current `balanceOf`
- `eth_getCode` to classify destination as EOA vs contract (best-effort)

Outputs
-------
- research/l1-bridge-recipient-followup.json
- research/l1-bridge-recipient-followup.md

Limitations
-----------
- CEX deposits are often per-user EOAs; on-chain we can rarely label them with
  high confidence without an external label dataset.
- "Bridge-out" happens on L2; the corresponding L1 release can happen later.
  This report focuses on recipient *outgoing transfers* on L1 over a block
  range you choose (defaults cover the Arbitrum-era window).
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
LPT_TOKEN_L1 = "0x58b6a8a3302369daec383334672404ee733ab239"

# ERC20 Transfer(address indexed from, address indexed to, uint256 value)
TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BALANCE_OF_SELECTOR = "0x70a08231"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

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
    def __init__(self, rpc_url: str, timeout_s: int = 60):
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
            headers={"content-type": "application/json", "user-agent": "livepeer-delegation-research/l1-bridge-followup"},
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
            "more than",
            "too many results",
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


def _latest_block(client: RpcClient) -> int:
    h = _rpc_with_retries(client, "eth_blockNumber", [])
    return int(str(h), 16)


def _balance_of(client: RpcClient, *, token: str, owner: str) -> int:
    owner = _normalize_address(owner)
    # ABI: balanceOf(address) → 32-byte padded address.
    data = BALANCE_OF_SELECTOR + ("0" * 24) + owner[2:]
    res = _rpc_with_retries(
        client,
        "eth_call",
        [{"to": _normalize_address(token), "data": data}, "latest"],
    )
    return int(str(res), 16)


def _get_code(client: RpcClient, addr: str) -> str:
    return str(_rpc_with_retries(client, "eth_getCode", [_normalize_address(addr), "latest"]) or "0x")


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
    if not path:
        return {}
    if not os.path.exists(path):
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
        # Keep only string values.
        out[addr] = {str(kk): str(vv) for kk, vv in v.items() if isinstance(kk, str) and isinstance(vv, str)}
    return out


@dataclass
class DestAgg:
    amount_wei: int = 0
    tx_count: int = 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eth-rpc", default=ETHEREUM_RPC_DEFAULT)
    parser.add_argument("--lpt-token", default=LPT_TOKEN_L1)
    parser.add_argument("--bridge-decode-json", default="research/arbitrum-bridge-out-decode.json")
    parser.add_argument("--labels-json", default="data/labels.json")
    parser.add_argument("--from-block", type=int, default=14_600_000)
    parser.add_argument("--to-block", type=int, default=0, help="0 = latest")
    parser.add_argument("--max-recipients", type=int, default=0, help="0 = all recipients")
    parser.add_argument("--out-md", default="research/l1-bridge-recipient-followup.md")
    parser.add_argument("--out-json", default="research/l1-bridge-recipient-followup.json")
    args = parser.parse_args()

    bridge = json.load(open(args.bridge_decode_json, "r", encoding="utf-8"))
    decoded = bridge.get("decoded_txs") or []
    if not isinstance(decoded, list) or not decoded:
        raise SystemExit(f"no decoded_txs in {args.bridge_decode_json}")

    # Build recipient totals from high-precision strings in decoded txs.
    bridged_by_recipient: Dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for row in decoded:
        if not isinstance(row, dict):
            continue
        to = row.get("l1_to")
        amt = row.get("amount_lpt")
        if not isinstance(to, str) or not isinstance(amt, str):
            continue
        bridged_by_recipient[_normalize_address(to)] += Decimal(amt)

    recipients = sorted(bridged_by_recipient.items(), key=lambda kv: kv[1], reverse=True)
    if int(args.max_recipients) > 0:
        recipients = recipients[: int(args.max_recipients)]

    labels = _load_labels(str(args.labels_json))

    client = RpcClient(str(args.eth_rpc))
    from_block = int(args.from_block)
    to_block = int(args.to_block) or _latest_block(client)
    if from_block >= to_block:
        raise SystemExit(f"from_block {from_block} >= to_block {to_block}")

    code_cache: Dict[str, bool] = {}

    def is_contract(addr: str) -> bool:
        a = _normalize_address(addr)
        if a in code_cache:
            return code_cache[a]
        code = _get_code(client, a)
        is_c = isinstance(code, str) and code != "0x" and len(code) > 2
        code_cache[a] = is_c
        return is_c

    per_recipient: List[Dict[str, Any]] = []
    global_category_totals_wei: Dict[str, int] = defaultdict(int)
    global_dest_totals: Dict[str, DestAgg] = defaultdict(DestAgg)

    for i, (recipient, bridged_lpt) in enumerate(recipients, start=1):
        bal_wei = _balance_of(client, token=str(args.lpt_token), owner=recipient)

        # Outgoing transfers from recipient.
        topics = [TOPIC0_TRANSFER, _pad_topic_address(recipient), None]
        logs = _get_logs_range(client, address=_normalize_address(args.lpt_token), topics=topics, from_block=from_block, to_block=to_block)

        dests: Dict[str, DestAgg] = defaultdict(DestAgg)
        for log in logs:
            try:
                _from, to, value_wei, _block, _tx = _decode_transfer_log(log)
            except Exception:
                continue
            dests[to].amount_wei += int(value_wei)
            dests[to].tx_count += 1
            global_dest_totals[to].amount_wei += int(value_wei)
            global_dest_totals[to].tx_count += 1

        dest_rows: List[Dict[str, Any]] = []
        category_totals_wei: Dict[str, int] = defaultdict(int)
        total_out_wei = 0
        total_out_txs = 0
        for dest, agg in dests.items():
            total_out_wei += int(agg.amount_wei)
            total_out_txs += int(agg.tx_count)
            label = labels.get(dest)
            if label and label.get("category"):
                cat = label["category"]
            elif dest == ZERO_ADDRESS:
                cat = "burn"
            else:
                cat = "unknown_contract" if is_contract(dest) else "unknown_eoa"
            category_totals_wei[cat] += int(agg.amount_wei)
            global_category_totals_wei[cat] += int(agg.amount_wei)
            dest_rows.append(
                {
                    "to": dest,
                    "category": cat,
                    "label": (label.get("name") if label else ""),
                    "amount_lpt": str(_wei_to_lpt(int(agg.amount_wei))),
                    "tx_count": int(agg.tx_count),
                }
            )

        dest_rows.sort(key=lambda r: Decimal(r["amount_lpt"]), reverse=True)

        per_recipient.append(
            {
                "rank": i,
                "recipient": recipient,
                "bridged_lpt": str(bridged_lpt),
                "current_balance_lpt": str(_wei_to_lpt(bal_wei)),
                "outgoing_lpt": str(_wei_to_lpt(total_out_wei)),
                "outgoing_tx_count": total_out_txs,
                "category_totals_lpt": {k: str(_wei_to_lpt(v)) for k, v in sorted(category_totals_wei.items())},
                "top_destinations": dest_rows[:15],
            }
        )

        print(f"[{i}/{len(recipients)}] {recipient} out={_format_lpt(_wei_to_lpt(total_out_wei))} LPT ({len(logs)} logs)")

    total_bridged = sum((bridged for _addr, bridged in bridged_by_recipient.items()), Decimal(0))

    total_outgoing_wei = sum((agg.amount_wei for agg in global_dest_totals.values()), 0)

    # Global top destinations
    top_global_dests = sorted(global_dest_totals.items(), key=lambda kv: kv[1].amount_wei, reverse=True)[:50]
    top_global_dests_rows: List[Dict[str, Any]] = []
    for dest, agg in top_global_dests:
        label = labels.get(dest)
        if label and label.get("category"):
            cat = label["category"]
        elif dest == ZERO_ADDRESS:
            cat = "burn"
        else:
            cat = "unknown_contract" if is_contract(dest) else "unknown_eoa"
        top_global_dests_rows.append(
            {
                "to": dest,
                "category": cat,
                "label": (label.get("name") if label else ""),
                "amount_lpt": str(_wei_to_lpt(int(agg.amount_wei))),
                "tx_count": int(agg.tx_count),
            }
        )

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "eth_rpc": str(args.eth_rpc),
        "lpt_token_l1": _normalize_address(args.lpt_token),
        "bridge_decode_json": str(args.bridge_decode_json),
        "labels_json": str(args.labels_json),
        "range": {"from_block": from_block, "to_block": to_block},
        "inputs": {
            "max_recipients": int(args.max_recipients),
            "bridged_recipients": len(recipients),
        },
        "totals": {
            "bridged_lpt": str(total_bridged),
            "outgoing_lpt": str(_wei_to_lpt(total_outgoing_wei)),
        },
        "category_totals": {k: str(_wei_to_lpt(v)) for k, v in sorted(global_category_totals_wei.items())},
        "top_destinations": top_global_dests_rows,
        "recipients": per_recipient,
    }

    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, sort_keys=True)
        f.write("\n")

    # Markdown output
    lines: List[str] = []
    lines.append("---")
    lines.append("title: L1 follow-up (bridge-outs)")
    lines.append(
        "description: Where major Arbitrum bridge-out recipients route LPT on Ethereum L1 (contracts vs EOAs vs labeled endpoints)."
    )
    lines.append("sidebar_label: L1 follow-up (bridge-outs)")
    lines.append("---")
    lines.append("")
    lines.append("# L1 follow-up for Arbitrum bridge-outs (LPT)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- L1 RPC: `{out_json['eth_rpc']}`")
    lines.append(f"- L1 LPT token: `{out_json['lpt_token_l1']}`")
    lines.append(f"- Inputs: `{out_json['bridge_decode_json']}` + `{out_json['labels_json']}`")
    lines.append(f"- L1 block range: `{from_block}` → `{to_block}`")
    lines.append(f"- Unique recipients analyzed: **{len(recipients)}**")
    lines.append(f"- Total bridged (decoded on L2): **{_format_lpt(Decimal(out_json['totals']['bridged_lpt']))} LPT**")
    lines.append(f"- Total outgoing on L1 (transfers from recipients): **{_format_lpt(Decimal(out_json['totals']['outgoing_lpt']))} LPT**")
    lines.append("")
    lines.append("## Key findings (from on-chain L1 transfers)")
    lines.append("")
    bridged_lpt = Decimal(out_json["totals"]["bridged_lpt"])
    outgoing_lpt = Decimal(out_json["totals"]["outgoing_lpt"])
    dex_lpt = Decimal(out_json["category_totals"].get("dex_router", "0"))
    exchange_lpt = Decimal(out_json["category_totals"].get("exchange", "0"))
    livepeer_lpt = Decimal(out_json["category_totals"].get("livepeer_contract", "0"))
    unknown_eoa_lpt = Decimal(out_json["category_totals"].get("unknown_eoa", "0"))
    unknown_contract_lpt = Decimal(out_json["category_totals"].get("unknown_contract", "0"))

    if bridged_lpt > 0:
        lines.append(f"- Outgoing / bridged ratio (upper bound): **{float(outgoing_lpt / bridged_lpt) * 100:.2f}%**")
    else:
        lines.append("- Outgoing / bridged ratio (upper bound): **n/a**")
    lines.append(f"- To `dex_router` (our small label set): **{_format_lpt(dex_lpt)} LPT**")
    lines.append(f"- To `exchange` (our small label set): **{_format_lpt(exchange_lpt)} LPT**")
    if livepeer_lpt > 0:
        lines.append(f"- To Livepeer contracts (labeled): **{_format_lpt(livepeer_lpt)} LPT**")
    if outgoing_lpt > 0:
        lines.append(f"- To unknown EOAs: **{_format_lpt(unknown_eoa_lpt)} LPT** ({float(unknown_eoa_lpt/outgoing_lpt)*100:.2f}%)")
        if unknown_contract_lpt > 0:
            lines.append(
                f"- To unknown contracts: **{_format_lpt(unknown_contract_lpt)} LPT** ({float(unknown_contract_lpt/outgoing_lpt)*100:.2f}%)"
            )
    lines.append("")
    lines.append(
        "Interpretation: in this sample, we do not observe whales routing bridged LPT to known DEX routers on L1. "
        "Most value goes to EOAs (potentially CEX deposit wallets or self-custody) plus Livepeer’s `L1 Escrow`. "
        "This is consistent with “bridge-out ≠ immediate DEX selling”, but it does not prove whether a given EOA sold on a CEX."
    )
    lines.append("")
    lines.append("## Category totals (outgoing)")
    lines.append("")
    lines.append("| Category | Outgoing (LPT) | Share |")
    lines.append("|---|---:|---:|")
    total_out_lpt = Decimal(out_json["totals"]["outgoing_lpt"])
    for cat, amt_str in out_json["category_totals"].items():
        amt = Decimal(amt_str)
        share = (amt / total_out_lpt) if total_out_lpt > 0 else Decimal(0)
        lines.append(f"| {cat} | {_format_lpt(amt)} | {float(share)*100:.2f}% |")
    lines.append("")
    lines.append("## Recipients (summary)")
    lines.append("")
    lines.append("| Rank | Recipient | Bridged (LPT) | Current balance (LPT) | Outgoing (LPT) | Out txs |")
    lines.append("|---:|---|---:|---:|---:|---:|")
    for r in per_recipient:
        lines.append(
            f"| {r['rank']} | `{r['recipient']}` | {_format_lpt(Decimal(r['bridged_lpt']))} | {_format_lpt(Decimal(r['current_balance_lpt']))} | {_format_lpt(Decimal(r['outgoing_lpt']))} | {int(r['outgoing_tx_count']):,} |"
        )
    lines.append("")
    lines.append("## Recipients (top destinations)")
    lines.append("")
    lines.append("Tip: expand only the wallets you care about.")
    lines.append("")
    for r in per_recipient:
        recipient = str(r["recipient"])
        bridged_fmt = _format_lpt(Decimal(r["bridged_lpt"]))
        outgoing_fmt = _format_lpt(Decimal(r["outgoing_lpt"]))
        txs = int(r["outgoing_tx_count"])
        lines.append("<details>")
        lines.append(
            f"<summary><code>{recipient}</code> — bridged <b>{bridged_fmt} LPT</b>, outgoing <b>{outgoing_fmt} LPT</b> ({txs:,} txs)</summary>"
        )
        lines.append("")
        lines.append(f"- Bridged (decoded on L2): **{bridged_fmt} LPT**")
        lines.append(f"- Current L1 LPT balance: **{_format_lpt(Decimal(r['current_balance_lpt']))} LPT**")
        lines.append(f"- Outgoing transfers in range: **{outgoing_fmt} LPT** across **{txs:,}** txs")
        lines.append("")
        lines.append("| Destination | Label | Category | Outgoing (LPT) | Txs |")
        lines.append("|---|---|---|---:|---:|")
        for drow in r["top_destinations"]:
            lines.append(
                f"| `{drow['to']}` | {drow.get('label','')} | {drow['category']} | {_format_lpt(Decimal(drow['amount_lpt']))} | {int(drow['tx_count']):,} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
